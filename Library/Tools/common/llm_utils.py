import os
import sys
import time
import threading
import concurrent.futures
import re
import json
import requests
from enum import Enum
from typing import List, Dict, Optional, Union

# Try to load keys from .env if present
def get_env_path():
    if getattr(sys, 'frozen', False):
        USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "AutoSub")
        return os.path.join(USER_DATA_DIR, ".env")
    
    # Search upwards for .env starting from current file
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr != os.path.dirname(curr): # Not at root
        potential = os.path.join(curr, ".env")
        if os.path.exists(potential): return potential
        curr = os.path.dirname(curr)
    return os.path.join(os.getcwd(), ".env")

ENV_PATH = get_env_path()

try:
    from dotenv import load_dotenv
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH)
    else:
        load_dotenv() 
except ImportError:
    pass

class LLMProvider(Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    MOONSHOT = "moonshot"
    DASHSCOPE = "dashscope"
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    SILICONFLOW = "siliconflow"

class RateLimiter:
    """Simple thread-safe rate limiter based on RPM."""
    def __init__(self, rpm: int):
        self.rpm = rpm
        self.interval = 60.0 / rpm
        self.last_request_time = 0
        self.lock = threading.Lock()

    def wait(self):
        sleep_time = 0
        with self.lock:
            current_time = time.time()
            next_available = self.last_request_time + self.interval
            if next_available > current_time:
                sleep_time = next_available - current_time
                self.last_request_time = next_available
            else:
                self.last_request_time = current_time
        if sleep_time > 0:
            time.sleep(sleep_time)

class LLMClient:
    def __init__(self, api_key: Optional[str] = None, provider: Optional[LLMProvider] = None):
        self.api_keys = {
            LLMProvider.GEMINI: api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
            LLMProvider.OPENAI: os.environ.get("OPENAI_API_KEY"),
            LLMProvider.MOONSHOT: os.environ.get("MOONSHOT_API_KEY"),
            LLMProvider.DASHSCOPE: os.environ.get("DASHSCOPE_API_KEY"),
            LLMProvider.ZHIPU: os.environ.get("ZHIPUAI_API_KEY") or os.environ.get("ZHIPU_API_KEY"),
            LLMProvider.DEEPSEEK: os.environ.get("DEEPSEEK_API_KEY"),
            LLMProvider.SILICONFLOW: os.environ.get("SILICONFLOW_API_KEY"),
        }
        
        # Default tier settings
        tier_str = os.environ.get("LLM_TIER", "tier1").lower()
        if tier_str == "free":
            self.rpm_limit = 10
            self.max_workers = 1
        elif tier_str == "tier1":
            self.rpm_limit = 100 
            self.max_workers = 10 
        else:
            self.rpm_limit = 500
            self.max_workers = 20
            
        self.limiter = RateLimiter(self.rpm_limit)
        self._gemini_configured = False

    def _get_provider(self, model_name: str) -> LLMProvider:
        model_name = model_name.lower()
        if "gpt" in model_name: return LLMProvider.OPENAI
        if "moonshot" in model_name or "kimi" in model_name: return LLMProvider.MOONSHOT
        if "qwen" in model_name: return LLMProvider.DASHSCOPE
        if "glm" in model_name: return LLMProvider.ZHIPU
        if "deepseek" in model_name: return LLMProvider.DEEPSEEK
        return LLMProvider.GEMINI

    def _call_openai_compatible(self, model_name: str, prompt: str, base_url: str, api_key: str) -> Optional[str]:
        if not api_key:
            print(f"❌ Error: API Key for {model_name} not found.")
            return None
            
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }
        
        self.limiter.wait()
        try:
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=data, timeout=60)
            response.raise_for_status()
            res_json = response.json()
            return res_json['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"❌ OpenAI-compatible API error ({model_name}): {e}")
            return None

    def _call_gemini(self, model_name: str, prompt: str) -> Optional[str]:
        api_key = self.api_keys[LLMProvider.GEMINI]
        if not api_key:
            print("❌ Error: Gemini API Key not found.")
            return None
            
        try:
            import google.generativeai as genai
            if not self._gemini_configured:
                genai.configure(api_key=api_key)
                self._gemini_configured = True
            
            model = genai.GenerativeModel(model_name)
            self.limiter.wait()
            response = model.generate_content(prompt)
            if response.text:
                return response.text.strip()
            return None
        except Exception as e:
            print(f"❌ Gemini API error: {e}")
            return None

    def generate_content(self, prompt: str, model_name: str = "gemini-1.5-flash", fallback: bool = True) -> Optional[str]:
        provider = self._get_provider(model_name)
        
        if provider == LLMProvider.GEMINI:
            return self._call_gemini(model_name, prompt)
        
        elif provider == LLMProvider.OPENAI:
            base_url = os.environ.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
            # Ensure no double /v1
            if base_url.endswith("/v1/"): base_url = base_url[:-1]
            return self._call_openai_compatible(model_name, prompt, base_url, self.api_keys[LLMProvider.OPENAI])
            
        elif provider == LLMProvider.MOONSHOT:
            return self._call_openai_compatible(model_name, prompt, "https://api.moonshot.cn/v1", self.api_keys[LLMProvider.MOONSHOT])
            
        elif provider == LLMProvider.DASHSCOPE:
            return self._call_openai_compatible(model_name, prompt, "https://dashscope.aliyuncs.com/compatible-mode/v1", self.api_keys[LLMProvider.DASHSCOPE])
            
        elif provider == LLMProvider.ZHIPU:
            return self._call_openai_compatible(model_name, prompt, "https://open.bigmodel.cn/api/paas/v4", self.api_keys[LLMProvider.ZHIPU])
            
        elif provider == LLMProvider.DEEPSEEK:
            return self._call_openai_compatible(model_name, prompt, "https://api.deepseek.com", self.api_keys[LLMProvider.DEEPSEEK])
            
        elif provider == LLMProvider.SILICONFLOW:
            return self._call_openai_compatible(model_name, prompt, "https://api.siliconflow.cn/v1", self.api_keys[LLMProvider.SILICONFLOW])
            
        return None

    def generate_batch(self, tasks: List[Dict], model_name: str = "gemini-1.5-flash") -> List[Dict]:
        results = []
        total = len(tasks)
        print(f"🚀 Starting batch generation for {total} items (Workers: {self.max_workers}, Model: {model_name})...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self.generate_content, task['prompt'], model_name): task 
                for task in tasks
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result_text = future.result()
                    results.append({**task, 'result': result_text})
                except Exception as e:
                    results.append({**task, 'result': None, 'error': str(e)})
                
                completed += 1
                print(f"   Progress: {completed}/{total} (chunks)", flush=True)
                    
        return results

    def _list_openai_models(self, provider: LLMProvider) -> List[str]:
        api_key = self.api_keys.get(provider)
        if not api_key:
            return []

        base_urls = {
            LLMProvider.OPENAI: "https://api.openai.com/v1",
            LLMProvider.MOONSHOT: "https://api.moonshot.cn/v1",
            LLMProvider.DASHSCOPE: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            LLMProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
            LLMProvider.DEEPSEEK: "https://api.deepseek.com",
            LLMProvider.SILICONFLOW: "https://api.siliconflow.cn/v1"
        }
        
        base_url = base_urls.get(provider)
        if not base_url:
            return []

        try:
            response = requests.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract names and filter for "stable" chat models
            models = []
            for m in data.get('data', []):
                m_id = m.get('id', '')
                # Filter out embedding, vision-only, or obscure assistant models
                low_id = m_id.lower()
                is_ignored = any(x in low_id for x in ['embedding', 'vector', 'search', 'text-moderation', 'whisper', 'dall-e', 'tts'])
                if m_id and not is_ignored:
                    models.append(m_id)
            
            # Smart Sorting: Put primary brand models at the top
            brand_map = {
                LLMProvider.DASHSCOPE: "qwen",
                LLMProvider.ZHIPU: "glm",
                LLMProvider.MOONSHOT: "moonshot",
                LLMProvider.DEEPSEEK: "deepseek"
            }
            brand = brand_map.get(provider, "")
            
            def sort_key(name):
                name_low = name.lower()
                # Priority 1: Starts with primary brand (e.g. qwen-)
                if brand and name_low.startswith(brand):
                    return (0, name_low)
                # Priority 2: Contains primary brand
                if brand and brand in name_low:
                    return (1, name_low)
                # Priority 3: Other models
                return (2, name_low)
            
            models.sort(key=sort_key)
            
            # Fallback if discovery returns nothing but we have key
            if not models:
                fallbacks = {
                    LLMProvider.OPENAI: ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
                    LLMProvider.MOONSHOT: ["moonshot-v1-8k", "moonshot-v1-32k"],
                    LLMProvider.DASHSCOPE: ["qwen-turbo", "qwen-max"],
                    LLMProvider.ZHIPU: ["glm-4-flash", "glm-4"],
                    LLMProvider.DEEPSEEK: ["deepseek-chat", "deepseek-reasoner"],
                    LLMProvider.SILICONFLOW: ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct-128K"]
                }
                return fallbacks.get(provider, [])
                
            return models
        except Exception as e:
            # Silently fallback to a safe list on error
            fallbacks = {
                LLMProvider.OPENAI: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                LLMProvider.MOONSHOT: ["moonshot-v1-8k", "moonshot-v1-32k"],
                LLMProvider.DASHSCOPE: ["qwen-turbo", "qwen-max", "qwen-plus"],
                LLMProvider.ZHIPU: ["glm-4-flash", "glm-4", "glm-4-air"],
                LLMProvider.DEEPSEEK: ["deepseek-chat", "deepseek-reasoner"],
                LLMProvider.SILICONFLOW: ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1"]
            }
            return fallbacks.get(provider, [])

    def list_models_by_provider(self, provider: LLMProvider) -> List[str]:
        api_key = self.api_keys.get(provider)
        if not api_key:
            return []
            
        if provider == LLMProvider.GEMINI:
            try:
                import google.generativeai as genai
                if not self._gemini_configured:
                    genai.configure(api_key=api_key)
                    self._gemini_configured = True
                models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        models.append(m.name.replace("models/", ""))
                return sorted(models)
            except: return []
            
        # Use dynamic discovery for all OpenAI-compatible providers
        return self._list_openai_models(provider)

    def list_accessible_models(self) -> List[str]:
        all_models = []
        for p in LLMProvider:
            all_models.extend(self.list_models_by_provider(p))
        return all_models

_CLIENT = None
def get_client():
    global _CLIENT
    if not _CLIENT:
        _CLIENT = LLMClient()
    return _CLIENT
