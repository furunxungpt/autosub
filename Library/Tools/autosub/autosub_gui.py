
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import subprocess
import threading
import sys
import os
import re
import json
import multiprocessing
import io
import ctypes
import io

# Force UTF-8 for stdout/stderr to handle emojis in logs on Windows
if sys.platform == "win32":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Configuration
if getattr(sys, 'frozen', False):
    # Dispatcher: If the first argument is a .py file, run it inside the frozen environment.
    # This is essential for subprocess calls to work within a single-EXE package.
    if len(sys.argv) > 1 and sys.argv[1].endswith('.py'):
        script_to_run = sys.argv[1]
        # Shift arguments so the script sees the correct sys.argv
        sys.argv = [sys.executable] + sys.argv[2:]
        try:
            import runpy
            runpy.run_path(script_to_run, run_name="__main__")
            sys.exit(0)
        except Exception as e:
            print(f"Error running bundled script {script_to_run}: {e}")
            sys.exit(1)

    BUNDLE_DIR = sys._MEIPASS
    CURRENT_DIR = os.path.join(BUNDLE_DIR, "Library", "Tools", "autosub")
    
    # Use User's Documents folder for writable data (settings, projects, .env)
    USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "AutoSub")
    if not os.path.exists(USER_DATA_DIR):
        try: os.makedirs(USER_DATA_DIR)
        except: USER_DATA_DIR = os.path.expanduser("~") # Fallback
        
    PROJECT_ROOT = USER_DATA_DIR 
    ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
    
    # Try reading key from app dir first (if portable), then user data dir
    if not os.path.exists(ENV_PATH):
        env_portable = os.path.join(os.path.dirname(sys.executable), ".env")
        if os.path.exists(env_portable):
            ENV_PATH = env_portable
        else:
            env_fallback = os.path.join(BUNDLE_DIR, ".env")
            if os.path.exists(env_fallback):
                ENV_PATH = env_fallback
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    # Anchor to true repository root d:\cc
    TOOLS_DIR = os.path.dirname(CURRENT_DIR)
    tmp_root = os.path.dirname(TOOLS_DIR)
    if os.path.basename(tmp_root).lower() == "library":
        PROJECT_ROOT = os.path.dirname(tmp_root)
    else:
        PROJECT_ROOT = tmp_root
    ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

AUTOSUB_SCRIPT = os.path.join(CURRENT_DIR, "autosub.py")
sys.path.append(os.path.join(CURRENT_DIR, "..", "common"))

try:
    import llm_utils
except ImportError:
    pass

class AutoSubGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoSub - 自动视频字幕生成工具 (Pro)")
        
        # Set Window Icon
        icon_path = os.path.join(CURRENT_DIR, "autosub.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
                # Fix for Taskbar icon in Windows
                myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception as e:
                print(f"Warning: Could not set icon: {e}")
        self.root.geometry("650x650")
        
        style = ttk.Style()
        style.configure("TLabel", font=("Microsoft YaHei", 9))
        style.configure("TButton", font=("Microsoft YaHei", 9))

        self.settings = {}
        self.last_was_progress = False
        # 1. Load factory defaults
        if getattr(sys, 'frozen', False):
            # When frozen, look in the App Root (where .exe is) for visibility
            APP_ROOT = os.path.dirname(sys.executable)
            defaults_file = os.path.join(APP_ROOT, "defaults.json")
            # If not there, fallback to the bundled internal one
            if not os.path.exists(defaults_file):
                defaults_file = os.path.join(CURRENT_DIR, "defaults.json")
        else:
            defaults_file = os.path.join(CURRENT_DIR, "defaults.json")

        if os.path.exists(defaults_file):
            try:
                with open(defaults_file, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except Exception: pass

        # 2. Load user settings (overrides)
        # Check Project Root (Documents/AutoSub) first, then App Root
        settings_locations = [os.path.join(PROJECT_ROOT, "settings.json")]
        if getattr(sys, 'frozen', False):
            settings_locations.append(os.path.join(os.path.dirname(sys.executable), "settings.json"))

        for settings_file in settings_locations:
            if os.path.exists(settings_file):
                try:
                    with open(settings_file, "r", encoding="utf-8") as f:
                        self.settings.update(json.load(f))
                except Exception: pass

        
        # --- Input Section ---
        input_frame = ttk.LabelFrame(root, text="输入源 (Input)", padding=10)
        input_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(input_frame, text="视频/URL:").grid(row=0, column=0, sticky="w")
        self.input_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.input_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(input_frame, text="选择...", command=self.browse_file).grid(row=0, column=2)
        
        tk.Label(input_frame, text="Cookies:").grid(row=1, column=0, sticky="w")
        self.cookies_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.cookies_var, width=50).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(input_frame, text="选择...", command=self.browse_cookies).grid(row=1, column=2)

        tk.Label(input_frame, text="项目根目录:").grid(row=2, column=0, sticky="w")
        self.output_dir_var = tk.StringVar(value=self.settings.get("output_dir", ""))
        ttk.Entry(input_frame, textvariable=self.output_dir_var, width=50).grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(input_frame, text="选择...", command=self.browse_output_dir).grid(row=2, column=2)

        # --- Settings Section ---
        settings_frame = ttk.LabelFrame(root, text="基础设置 (Basic Settings)", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        
        # API Vendor Row
        tk.Label(settings_frame, text="模型厂商:").grid(row=0, column=0, sticky="w")
        self.vendor_display_map = {
            "Google Gemini": "gemini",
            "OpenAI (ChatGPT)": "openai",
            "Moonshot (Kimi)": "moonshot",
            "Alibaba (Qwen)": "dashscope",
            "Zhipu (GLM)": "zhipu",
            "DeepSeek": "deepseek",
            "Silicon Flow (硅基流动)": "siliconflow"
        }
        vendor_default = self.settings.get("llm_vendor", "Google Gemini")
        self.vendor_var = tk.StringVar(value=vendor_default)
        self.vendor_combo = ttk.Combobox(settings_frame, textvariable=self.vendor_var, values=list(self.vendor_display_map.keys()), width=15, state="readonly")
        self.vendor_combo.grid(row=0, column=1, sticky="w", padx=5)
        self.vendor_combo.bind("<<ComboboxSelected>>", self.on_vendor_change)

        # LLM Model (Translation)
        tk.Label(settings_frame, text="选择模型:").grid(row=0, column=2, sticky="w", padx=10)
        self.llm_model_var = tk.StringVar(value=self.settings.get("llm_model", "gemini-3.1-pro-preview"))
        self.llm_combo = ttk.Combobox(settings_frame, textvariable=self.llm_model_var, values=[], width=22, state="disabled")
        self.llm_combo.grid(row=0, column=3, sticky="w", padx=5)
        
        self.default_btn = ttk.Button(settings_frame, text="设为默认", width=8, command=self.save_as_default)
        self.default_btn.grid(row=0, column=4, sticky="w", padx=5)

        # API Key Row
        tk.Label(settings_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(settings_frame, textvariable=self.api_key_var, width=35, show="*")
        self.api_key_entry.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)
        
        ttk.Button(settings_frame, text="保存该密钥", command=self.save_current_vendor_key, width=12).grid(row=1, column=3, sticky="w", padx=5)
        
        # Test Connection Button
        self.test_btn = ttk.Button(settings_frame, text="测试连接", width=8, command=self.test_api)
        self.test_btn.grid(row=1, column=4, sticky="w", padx=5)
        
        # Whisper Model row
        tk.Label(settings_frame, text="转录模型:").grid(row=2, column=0, sticky="w")
        self.model_var = tk.StringVar(value=self.settings.get("model", "large-v2"))
        ttk.Combobox(settings_frame, textvariable=self.model_var, values=["large-v3-turbo", "large-v3", "large-v2", "medium"], width=15, state="readonly").grid(row=2, column=1, sticky="w", padx=5)

        # Tone Selection (Style)
        tk.Label(settings_frame, text="内容语气:").grid(row=2, column=2, sticky="w", padx=10)
        self.style_var = tk.StringVar(value=self.settings.get("style", "casual"))
        ttk.Combobox(settings_frame, textvariable=self.style_var, values=["casual", "formal", "edgy"], width=15, state="readonly").grid(row=2, column=3, sticky="w", padx=5)

        self.model_status_label = tk.Label(settings_frame, text="", fg="red", font=("Microsoft YaHei", 8))
        self.model_status_label.grid(row=2, column=4, sticky="w")
        
        # Start async initial load
        self.on_vendor_change(None)

        # --- Advanced Style Section ---
        style_frame = ttk.LabelFrame(root, text="字幕样式 (Subtitle Style)", padding=10)
        style_frame.pack(fill="x", padx=10, pady=5)
        
        # Ro
        # w 0: Layout & Position
        tk.Label(style_frame, text="布局模式:").grid(row=0, column=0, sticky="w")
        self.layout_var = tk.StringVar(value=self.settings.get("layout", "bilingual"))
        ttk.Combobox(style_frame, textvariable=self.layout_var, values=["bilingual", "cn", "en"], width=12, state="readonly").grid(row=0, column=1, sticky="w", padx=5)
        
        tk.Label(style_frame, text="首选语言 (置于上方):").grid(row=0, column=2, sticky="w", padx=10)
        self.main_lang_var = tk.StringVar(value=self.settings.get("main_lang", "cn"))
        ttk.Combobox(style_frame, textvariable=self.main_lang_var, values=["cn", "en"], width=8, state="readonly").grid(row=0, column=3, sticky="w", padx=5)
        
        # Row 1: Font
        # Row 1: Font
        # Get System Fonts
        try:
            self.available_fonts = sorted(list(set(font.families())))
        except:
            self.available_fonts = ["Arial", "Microsoft YaHei", "SimHei", "KaiTi", "Times New Roman"]

        # Keep map mainly for legacy manual aliases if any, but now we prefer system names
        self.font_map_cn = {"楷体": "KaiTi", "微软雅黑": "Microsoft YaHei", "黑体": "SimHei", "宋体": "SimSun", "仿宋": "FangSong"}

        tk.Label(style_frame, text="中文字体:").grid(row=1, column=0, sticky="w", pady=2)
        # Default to STKaiti (华文楷体) if available, then KaiTi, else Microsoft YaHei
        target_font_cn = "STKaiti" # 华文楷体
        if target_font_cn not in self.available_fonts:
             # Try Chinese name if English name not found
             if "华文楷体" in self.available_fonts: target_font_cn = "华文楷体"
             elif "KaiTi" in self.available_fonts: target_font_cn = "KaiTi"
             elif "Microsoft YaHei" in self.available_fonts: target_font_cn = "Microsoft YaHei"
             else: target_font_cn = self.available_fonts[0]

        default_cn = target_font_cn
        
        self.cn_font_var = tk.StringVar(value=self.settings.get("cn_font", default_cn))
        ttk.Combobox(style_frame, textvariable=self.cn_font_var, values=self.available_fonts, width=20, state="readonly").grid(row=1, column=1, padx=5)
        
        tk.Label(style_frame, text="英文字体:").grid(row=1, column=2, sticky="w", padx=10)
        default_en = "Arial" if "Arial" in self.available_fonts else self.available_fonts[0]
        self.en_font_var = tk.StringVar(value=self.settings.get("en_font", default_en))
        # Changed Entry to Combobox
        ttk.Combobox(style_frame, textvariable=self.en_font_var, values=self.available_fonts, width=20, state="readonly").grid(row=1, column=3, padx=5)
        
        # Row 2: Size
        tk.Label(style_frame, text="中文大小:").grid(row=2, column=0, sticky="w", pady=2)
        self.cn_size_var = tk.StringVar(value=self.settings.get("cn_size", "60"))
        ttk.Entry(style_frame, textvariable=self.cn_size_var, width=5).grid(row=2, column=1, sticky="w", padx=5)
        
        tk.Label(style_frame, text="英文大小:").grid(row=2, column=2, sticky="w", padx=10)
        self.en_size_var = tk.StringVar(value=self.settings.get("en_size", "36"))
        ttk.Entry(style_frame, textvariable=self.en_size_var, width=5).grid(row=2, column=3, sticky="w", padx=5)
        
        # Row 3: Color
        colors = ["Yellow", "White", "Gold", "Black", "Blue", "Green"]
        tk.Label(style_frame, text="中文颜色:").grid(row=3, column=0, sticky="w", pady=2)
        self.cn_color_var = tk.StringVar(value=self.settings.get("cn_color", "Gold"))
        ttk.Combobox(style_frame, textvariable=self.cn_color_var, values=colors, width=12, state="readonly").grid(row=3, column=1, sticky="w", padx=5)
        
        tk.Label(style_frame, text="英文颜色:").grid(row=3, column=2, sticky="w", padx=10)
        self.en_color_var = tk.StringVar(value=self.settings.get("en_color", "White"))
        ttk.Combobox(style_frame, textvariable=self.en_color_var, values=colors, width=12, state="readonly").grid(row=3, column=3, sticky="w", padx=5)
        
        # Row 4: Utils
        self.bg_box_var = tk.BooleanVar(value=bool(self.settings.get("bg_box", True)))
        ttk.Checkbutton(style_frame, text="启用背景框 (Background Box)", variable=self.bg_box_var).grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        # --- Log Section ---
        log_frame = ttk.LabelFrame(root, text="日志与进度 (Log & Progress)", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Progress Bar added here
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(log_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill="x", padx=5, pady=5)
        self.status_label = tk.Label(log_frame, text="等待任务...", font=("Microsoft YaHei", 8))
        self.status_label.pack(fill="x")
        
        # Text with Scrollbar
        self.log_text = tk.Text(log_frame, height=8, state="disabled", font=("Consolas", 9))
        self.log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        
        self.log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        
        # --- Actions ---
        action_frame = ttk.Frame(root, padding=10)
        action_frame.pack(fill="x")
        
        self.start_btn = ttk.Button(action_frame, text="开始处理 (Start Process)", command=self.start_process)
        self.start_btn.pack(side="right", padx=5)
        
        # Override exit to kill processes
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        ttk.Button(action_frame, text="退出 (Exit)", command=self.on_close).pack(side="right")
        
        # Ensure bottom visible
        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())

    def on_close(self):
        # Kill any running subprocesses
        # We only track the main one, but if we launched valid threads, we should let them die or kill them?
        # Python threads are hard to kill. But the subprocess should be killed.
        # We need to track the active subprocess object.
        if hasattr(self, 'current_process') and self.current_process:
             try:
                 self.current_process.kill()
             except: pass
        self.root.destroy()
        sys.exit(0)

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv"), ("All", "*.*")])
        if filename: self.input_var.set(filename)
            
    def browse_cookies(self):
        filename = filedialog.askopenfilename(filetypes=[("Txt", "*.txt")])
        if filename: self.cookies_var.set(filename)

    def browse_output_dir(self):
        dirname = filedialog.askdirectory()
        if dirname: self.output_dir_var.set(dirname)

    def log_clear(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.config(state="disabled")

    def log(self, message):
        self.log_text.config(state="normal")
        
        # If the last line was a Progress update and this one is too, replace it instead of appending
        is_progress = "Progress:" in message or ("[download]" in message and "%" in message)
        if is_progress and getattr(self, "last_was_progress", False):
            # Delete the last line. "end-1c" is the character before the very end (the last newline)
            # "end-2l" goes back to the start of the line before the last one.
            self.log_text.delete("end-2l", "end-1c")
        
        self.log_text.insert("end", message + "\n")
        self.last_was_progress = is_progress
        
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        
        # Parse progress
        # Expected: Progress: 12.3% (00:01:23,456 / 00:10:00,000)
        # Or: [download]  12.3% of 100MiB ...
        if is_progress:
            try:
                pct_match = re.search(r"(\d+\.?\d*)%", message)
                if pct_match:
                    self.progress_var.set(float(pct_match.group(1)))
                    self.status_label.config(text=message.strip())
            except: pass
        elif "🎬" in message or "🎙️" in message or "🌍" in message or "🔥" in message:
             self.status_label.config(text=message.strip())
             if "🎬" in message: self.progress_var.set(5)
             if "🎙️" in message: self.progress_var.set(10)
             if "🌍" in message: self.progress_var.set(80)
             if "🔥" in message: self.progress_var.set(90)

    def start_process(self):
        input_val = self.input_var.get()
        if not input_val:
            messagebox.showerror("错误", "请输入视频链接或文件")
            return
            
        self.start_btn.config(state="disabled", text="处理中...")
        self.start_btn.config(state="disabled", text="处理中...")
        self.log_clear()
        self.log(f"--- 任务启动: {input_val} ---")
        self.progress_var.set(0)
        
        cmd = [sys.executable, AUTOSUB_SCRIPT, input_val]
        cmd.extend(["--model", self.model_var.get()])
        cmd.extend(["--llm-model", self.llm_model_var.get()])
        cmd.extend(["--style", self.style_var.get()])
        
        # Advanced Layout Args
        cmd.extend(["--layout", self.layout_var.get()])
        cmd.extend(["--main-lang", self.main_lang_var.get()])
        
        # Format font name from Chinese label to English ID for ASS compatibility if needed
        cn_font = self.cn_font_var.get()
        real_cn_font = self.font_map_cn.get(cn_font, cn_font)
        
        cmd.extend(["--cn-font", real_cn_font])
        cmd.extend(["--en-font", self.en_font_var.get()])
        cmd.extend(["--cn-size", self.cn_size_var.get()])
        cmd.extend(["--en-size", self.en_size_var.get()])
        cmd.extend(["--cn-color", self.cn_color_var.get()])
        cmd.extend(["--en-color", self.en_color_var.get()])
        
        if not self.bg_box_var.get():
            cmd.append("--no-bg-box")
        
        if self.cookies_var.get():
            cmd.extend(["--cookies", self.cookies_var.get()])
            
        if self.output_dir_var.get():
            cmd.extend(["--output-dir", self.output_dir_var.get()])
            
        threading.Thread(target=self.run_subprocess, args=(cmd,), daemon=True).start()

    def run_subprocess(self, cmd):
        try:
            # force utf-8 env for python to avoid encoding issues
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"
            
            # Store process ref for killing
            self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', env=env, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            process = self.current_process
            
            for line in process.stdout:
                msg = line.strip()
                self.root.after(0, self.log, msg)
                
            process.wait()
            
            if process.returncode == 0:
                self.root.after(0, lambda: self.progress_var.set(100))
                self.root.after(0, lambda: self.status_label.config(text="任务已完成！"))
                # self.root.after(0, lambda: messagebox.showinfo("完成", "视频处理完毕！"))  <-- DISABLED
            else:
                self.root.after(0, lambda: self.status_label.config(text="任务失败"))
                self.root.after(0, lambda: messagebox.showerror("错误", "任务失败，请检查日志"))
                
        except Exception as e:
            self.root.after(0, self.log, f"System Error: {e}")
        finally:
            self.root.after(0, lambda: self.start_btn.config(state="normal", text="开始处理 (Start Process)"))


    def on_vendor_change(self, event):
        vendor_name = self.vendor_var.get()
        vendor_id = self.vendor_display_map[vendor_name]
        
        # Map vendor_id to env key
        env_map = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "zhipu": "ZHIPUAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY"
        }
        env_key = env_map[vendor_id]
        
        current_key = os.environ.get(env_key, "")
        self.api_key_var.set(current_key)
        
        # Update model list
        # If the current model is already the one in settings, don't show "Loading..." to avoid flicker/racing
        if self.llm_model_var.get() != self.settings.get("llm_model") or vendor_name != self.settings.get("llm_vendor"):
            self.llm_model_var.set("正在获取模型...")
            
        self.llm_combo.config(state="disabled")
        threading.Thread(target=self.fetch_models_for_vendor, args=(vendor_id, env_key), daemon=True).start()

    def fetch_models_for_vendor(self, vendor_id, env_key):
        try:
            from llm_utils import LLMProvider, LLMClient
            provider = LLMProvider(vendor_id)
            client = LLMClient() # Will use existing env vars
            
            models = client.list_models_by_provider(provider)
            
            if models:
                 self.root.after(0, lambda: self.update_model_ui(models, True))
            else:
                 msg = "缺少 Key" if not os.environ.get(env_key) else "无可获取模型"
                 self.root.after(0, lambda: self.update_model_ui([], False, msg))
        except Exception as e:
            self.root.after(0, lambda: self.update_model_ui([], False, "连接失败"))

    def update_model_ui(self, models, success, error_msg=""):
        if success:
            self.llm_combo.config(state="readonly", values=models)
            current = self.llm_model_var.get()
            saved_model = self.settings.get("llm_model")
            saved_vendor = self.settings.get("llm_vendor")
            current_vendor = self.vendor_var.get()

            # Logic to decide which model to select:
            # 1. If current value is valid and in the list, keep it.
            # 2. If it's the saved vendor and the saved model is in the list, use it.
            # 3. Fallback to common stable models.
            
            if current in models:
                pass # Keep it
            elif current_vendor == saved_vendor and saved_model in models:
                self.llm_model_var.set(saved_model)
            else:
                if "gemini-1.5-flash" in models: self.llm_model_var.set("gemini-1.5-flash")
                elif "gpt-4o-mini" in models: self.llm_model_var.set("gpt-4o-mini")
                elif "glm-4-flash" in models: self.llm_model_var.set("glm-4-flash")
                elif "moonshot-v1-8k" in models: self.llm_model_var.set("moonshot-v1-8k")
                elif "deepseek-chat" in models: self.llm_model_var.set("deepseek-chat")
                elif "deepseek-ai/DeepSeek-V3" in models: self.llm_model_var.set("deepseek-ai/DeepSeek-V3")
                elif models: self.llm_model_var.set(models[0])
                
            self.model_status_label.config(text="")
        else:
            self.llm_combo.config(state="disabled")
            self.llm_model_var.set("不可用")
            self.model_status_label.config(text=f"⚠️ {error_msg}")

    def save_current_vendor_key(self):
        vendor_name = self.vendor_var.get()
        vendor_id = self.vendor_display_map[vendor_name]
        key = self.api_key_var.get().strip()
        
        env_map = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "zhipu": "ZHIPUAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY"
        }
        env_key = env_map[vendor_id]
        
        self.save_api_keys({env_key: key})
            
    def open_keys_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("API 密钥配置 (LLM Keys)")
        dialog.geometry("450x400")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Load current keys from env
        keys_to_vars = {
            "GEMINI_API_KEY": tk.StringVar(value=os.environ.get("GEMINI_API_KEY", "")),
            "OPENAI_API_KEY": tk.StringVar(value=os.environ.get("OPENAI_API_KEY", "")),
            "MOONSHOT_API_KEY": tk.StringVar(value=os.environ.get("MOONSHOT_API_KEY", "")),
            "DASHSCOPE_API_KEY": tk.StringVar(value=os.environ.get("DASHSCOPE_API_KEY", "")),
            "ZHIPUAI_API_KEY": tk.StringVar(value=os.environ.get("ZHIPUAI_API_KEY", "")),
            "DEEPSEEK_API_KEY": tk.StringVar(value=os.environ.get("DEEPSEEK_API_KEY", "")),
            "SILICONFLOW_API_KEY": tk.StringVar(value=os.environ.get("SILICONFLOW_API_KEY", "")),
        }

        labels = [
            ("Gemini API Key:", "GEMINI_API_KEY"),
            ("OpenAI API Key:", "OPENAI_API_KEY"),
            ("Moonshot (Kimi):", "MOONSHOT_API_KEY"),
            ("DashScope (Qwen):", "DASHSCOPE_API_KEY"),
            ("Zhipu (GLM):", "ZHIPUAI_API_KEY"),
            ("DeepSeek Key:", "DEEPSEEK_API_KEY"),
            ("Silicon Flow:", "SILICONFLOW_API_KEY"),
        ]

        for i, (label_text, key_name) in enumerate(labels):
            tk.Label(dialog, text=label_text).grid(row=i, column=0, padx=10, pady=5, sticky="e")
            entry = ttk.Entry(dialog, textvariable=keys_to_vars[key_name], width=40, show="*")
            entry.grid(row=i, column=1, padx=10, pady=5, sticky="w")

        def perform_save():
            new_keys = {k: v.get().strip() for k, v in keys_to_vars.items()}
            self.save_api_keys(new_keys)
            # Update the main window reference if Gemini was changed
            if new_keys["GEMINI_API_KEY"]:
                self.api_key_var.set(new_keys["GEMINI_API_KEY"])
            dialog.destroy()

        ttk.Button(dialog, text="保存并更新 (Save & Update)", command=perform_save).grid(row=len(labels), column=0, columnspan=2, pady=15)

    def save_api_keys(self, keys_dict):
        """Saves a dictionary of API keys to env and .env file."""
        try:
            # 1. Update Env Var
            for k, v in keys_dict.items():
                if v: os.environ[k] = v
            
            # 2. Write to .env
            lines = []
            if os.path.exists(ENV_PATH):
                with open(ENV_PATH, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            
            # Key value map for replacement
            current_config = {}
            for line in lines:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    current_config[k.strip()] = v.strip()
            
            # Update with new keys
            for k, v in keys_dict.items():
                if v: current_config[k] = v
                
            # Reconstruct .env
            with open(ENV_PATH, 'w', encoding='utf-8') as f:
                for k, v in current_config.items():
                    f.write(f"{k}={v}\n")
                
            # Reload clients
            llm_utils._CLIENT = None
               
            messagebox.showinfo("成功", "API Keys 已保存并更新配置！")
            
            # Refresh Models
            self.model_status_label.config(text="刷新中...")
            self.on_vendor_change(None)
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def save_as_default(self):
        """Saves current vendor and model to settings.json."""
        self.settings['llm_vendor'] = self.vendor_var.get()
        self.settings['llm_model'] = self.llm_model_var.get()
        self.settings['output_dir'] = self.output_dir_var.get()
        
        settings_file = os.path.join(PROJECT_ROOT, "settings.json")
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("成功", f"默认配置已保存：\n厂商：{self.settings['llm_vendor']}\n模型：{self.settings['llm_model']}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def test_api(self):
        # Disable button first
        self.test_btn.config(state="disabled", text="Testing...")
        threading.Thread(target=self._run_test_api, daemon=True).start()

    def _run_test_api(self):
        try:
            from llm_utils import LLMClient
            client = LLMClient()
            model_name = self.llm_model_var.get()
            
            # Sanity check
            if not model_name or "连接" in model_name or "加载" in model_name: 
                model_name = "gemini-1.5-flash"
            
            # Try a simple prompt
            res = client.generate_content("Say OK", model_name=model_name)
            
            def show_ok():
                messagebox.showinfo("测试成功", f"API 连接正常！\n响应: {str(res)}")
                self.test_btn.config(state="normal", text="测试连接")
                # Refresh list if it was empty
                if not self.llm_combo['values']:
                   self.on_vendor_change(None)
                   
            def show_fail(msg):
                messagebox.showerror("测试失败", msg)
                self.test_btn.config(state="normal", text="测试连接")

            if res:
                self.root.after(0, show_ok)
            else:
                 self.root.after(0, lambda: show_fail("API返回为空或连接被拒绝。"))
                 
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("测试异常", f"连接错误: {str(e)}"))
            self.root.after(0, lambda: self.test_btn.config(state="normal", text="测试连接"))

if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = AutoSubGUI(root)
    root.mainloop()
