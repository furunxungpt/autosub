
import os
import sys
import argparse
import math
import time
import re
from typing import List, Dict
import io

# Force UTF-8 for stdout/stderr to handle emojis in logs on Windows (essential for pythonw)
if sys.platform == "win32":
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass

# Configuration
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    TOOLS_DIR = os.path.join(BUNDLE_DIR, "Library", "Tools")
    USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "AutoSub")
    ENV_PATH = os.path.join(USER_DATA_DIR, ".env")
else:
    TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(TOOLS_DIR)), ".env")

sys.path.append(os.path.join(TOOLS_DIR, "subtranslator", "lib"))
sys.path.append(os.path.join(TOOLS_DIR, "common"))

try:
    import gemini_utils
except ImportError as e:
    print(f"Warning: gemini_utils not found ({e}). Using llm_utils only.")

try:
    import srt_utils
except ImportError as e:
    print(f"❌ Error: srt_utils is mandatory and was not found: {e}")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)

# --- SKILL INTEGRATION ---

def load_skill_rules(tool_name):
    """
    Reads the README/SKILL.md of a tool to extract prompting rules.
    """
    skill_dir = os.path.join(TOOLS_DIR, tool_name)
    readme_path = os.path.join(skill_dir, "README.md")
    content = ""
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
    return content

# Load rules once at startup
HUMANIZER_RULES = load_skill_rules("humanizer-zh")
VERBALIZER_RULES = load_skill_rules("verbalizer")
SUBTRANSLATOR_RULES = load_skill_rules("subtranslator")



# Retrieve API Keys from environment
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)
except ImportError:
    pass

import llm_utils
client = llm_utils.get_client()

def get_context_window(blocks: List[Dict], index: int, window_size: int = 2) -> Dict:
    """
    Returns context lines (before/after) for a given block index.
    """
    start = max(0, index - window_size)
    end = min(len(blocks), index + window_size + 1)
    
    prev_text = " ".join([" ".join(b['lines']) for b in blocks[start:index]])
    next_text = " ".join([" ".join(b['lines']) for b in blocks[index+1:end]])
    
    return {"prev": prev_text, "next": next_text}

def smart_translate_chunk(chunk_blocks: List[Dict], style: str = "casual", model_name: str = "gemini-1.5-flash") -> List[Dict]:
    """
    Translates a chunk of subtitle blocks using context-aware prompting.
    """
    # Construct the Prompt
    input_text = ""
    for i, block in enumerate(chunk_blocks):
        # We simplify the input to line format: [ID] Text
        text = " ".join(block['lines']).replace("\n", " ")
        input_text += f"[{block['index']}] {text}\n"

    prompt = f"""
You are an expert subtitle translator and editor.
Translate the following English subtitles into Simplified Chinese.

### STEP 1: VERBALIZATION (Tone & Persona)
{VERBALIZER_RULES[:1500]}... (Truncated for brevity)
TARGET STYLE: {style}
- "Casual": Natural, spoken Chinese. Use "其实", "也就是说".
- "Tech": Accurate terminology. "Code" -> "代码", "Agent" -> "智能体".
- "Edgy": Short, punchy, impactful.

### STEP 2: HUMANIZATION (De-AI)
{HUMANIZER_RULES[:1500]}... (Truncated for brevity)
- NO "translationese".
- NO "此外", "意味着", "不可或缺".
- NO long dashes "——".
- Vary sentence length.

### STEP 3: CONTEXT AWARENESS
- Use the provided Context Lines (if any) to understand the meaning, but ONLY translate the Target Line.
- If a sentence is split across lines, translate the PARTIAL meaning naturaly for that time slot.

INPUT BLOCK:
{input_text}

OUTPUT FORMAT:
[ID] Translated Text
...
"""
    
    try:
        translated_text = client.generate_content(prompt, model_name=model_name)
        if not translated_text:
            return chunk_blocks
            
        # Parse the Output
        translated_map = {}
        for line in translated_text.split('\n'):
            match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
            if match:
                idx = match.group(1)
                content = match.group(2).strip()
                translated_map[idx] = content
        
        # Apply translations back to blocks
        translated_blocks = []
        for block in chunk_blocks:
            new_block = block.copy()
            idx = str(block['index']) # Ensure string comparison
            if idx in translated_map:
                new_block['lines'] = [translated_map[idx]]
            else:
                # Fallback: keep original if translation missing (better than empty)
                print(f"Warning: Missing translation for block {idx}")
                new_block['lines'] = block['lines'] 
            translated_blocks.append(new_block)
            
        return translated_blocks

    except Exception as e:
        print(f"Error translating chunk: {e}")
        return chunk_blocks # Return original on failure


STYLE_GUIDE_PATH = os.path.join(TOOLS_DIR, "common", "STYLE_GUIDE.md")

def load_regex_rules(filepath):
    rules = []
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith("|") and not line.startswith("| Rule") and not line.startswith("| description") and not line.startswith("|---"):
                    parts = [p.strip() for p in re.split(r'(?<!\\)\|', line) if p.strip()]
                    if len(parts) >= 2:
                        pattern = parts[1].strip('`').replace(r'\|', '|') # Remove markdown code ticks and unescape pipes
                        replacement = parts[2].strip('`').replace(r'\|', '|') if len(parts) > 2 else ""
                        rules.append((pattern, replacement))
    return rules

REGEX_RULES = load_regex_rules(STYLE_GUIDE_PATH)

def humanize_text(text: str) -> str:
    """
    Applies configured Regex rules and basic Humanizer cleanup.
    """
    # 0. Apply Regex Rules from STYLE_GUIDE.md
    for pattern, replacement in REGEX_RULES:
        try:
            text = re.sub(pattern, replacement, text)
        except Exception as e:
            # print(f"Regex error: {e} pattern={pattern}")
            pass

    # 1. Remove common AI connectors (Hardcoded fallbacks)
    text = text.replace("此外，", "另外，")
    text = text.replace("总而言之，", "简单说，")
    text = text.replace("不可或缺", "很重要")
    text = text.replace("意味着", "说明")
    
    # 2. Fix punctuation
    text = text.replace(",", "，").replace("?", "？").replace("!", "！")
    
    # 3. Trim extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def is_untranslated(block: Dict) -> bool:
    """
    Returns True if a block has not been successfully translated.
    Detects: empty lines, known marker tags, or predominantly English text.
    Blocks containing any CJK characters are always considered translated
    (proper nouns like 'Palantir' mixed with Chinese are valid).
    """
    text = " ".join(block.get('lines', [])).strip()
    if not text:
        return True
    markers = ['[UNTRANSLATED]', '[TRANSLATION_FAILED]']
    if any(m in text for m in markers):
        return True
    # If there's any Chinese, it's a valid (possibly mixed) translation
    if re.search(r'[\u4e00-\u9fff]', text):
        return False
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return False
    ascii_ratio = sum(1 for c in alpha if ord(c) < 128) / len(alpha)
    return ascii_ratio > 0.7 and len(alpha) >= 8


def translate_blocks(blocks: List[Dict], client, model: str, style: str,
                     verbalizer_snippet: str, humanizer_snippet: str,
                     knowledge_snippet: str) -> List[Dict]:
    """
    Translates a list of blocks (may be any size) using generate_batch.
    Returns the blocks with translations applied. Does NOT apply humanize_text.
    Original text is kept as fallback for any block whose translation is missing/empty.
    """
    BATCH = 20
    total = len(blocks)
    tasks = []

    for i in range(0, total, BATCH):
        chunk = blocks[i:i + BATCH]
        input_text = ""
        for block in chunk:
            text = " ".join(block['lines']).replace("\n", " ").strip()
            input_text += f"[{block['index']}] {text}\n"

        prompt = f"""You are an expert subtitle translator and editor.
Translate the following English subtitles into Simplified Chinese.

### STEP 1: VERBALIZATION (Tone & Persona)
{verbalizer_snippet}...
TARGET STYLE: {style}

### STEP 2: DOMAIN KNOWLEDGE & ASR CORRECTION
{knowledge_snippet}

### STEP 3: HUMANIZATION (De-AI)
{humanizer_snippet}...

### STEP 4: CONTEXT AWARENESS
INPUT BLOCK:
{input_text}

OUTPUT FORMAT (STRICT — one line per segment, no extra text):
[ID] Translated Text
...
"""
        tasks.append({'index': i // BATCH, 'chunk': chunk, 'prompt': prompt})

    results = client.generate_batch(tasks, model)
    results.sort(key=lambda x: x['index'])

    # Build a map of all translations
    translated_map = {}
    for res in results:
        result_text = res.get('result')
        if result_text:
            for line in result_text.split('\n'):
                match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
                if match:
                    idx = match.group(1)
                    content = match.group(2).strip()
                    if content:  # guard: reject empty translations
                        translated_map[idx] = content

    # Apply translations; fall back to original text if missing
    out = []
    for block in blocks:
        new_block = block.copy()
        idx = str(block['index'])
        if idx in translated_map:
            new_block['lines'] = [translated_map[idx]]
        # else: keep whatever was there (original EN or previous attempt)
        out.append(new_block)
    return out


def postprocess_retry_loop(final_blocks: List[Dict], client, model: str, style: str,
                            verbalizer_snippet: str, humanizer_snippet: str,
                            knowledge_snippet: str, max_iterations: int = 5) -> List[Dict]:
    """
    Iteratively re-translates any untranslated/empty blocks until all are done
    (or max_iterations is reached). Returns final_blocks with all translations filled.
    Does NOT apply humanize_text — that is done in a single pass after this function.
    """
    for iteration in range(1, max_iterations + 1):
        missed_positions = [i for i, b in enumerate(final_blocks) if is_untranslated(b)]
        if not missed_positions:
            print(f"✅ Post-processing complete after {iteration - 1} extra pass(es). All segments translated.")
            break

        print(f"🔄 Post-processing pass {iteration}/{max_iterations}: "
              f"{len(missed_positions)} untranslated segment(s) detected. Re-translating...")

        missed_blocks = [final_blocks[i] for i in missed_positions]
        retranslated = translate_blocks(
            missed_blocks, client, model, style,
            verbalizer_snippet, humanizer_snippet, knowledge_snippet
        )

        # Re-insert results at original positions
        for pos, new_block in zip(missed_positions, retranslated):
            final_blocks[pos] = new_block

        # Report remaining
        still_missed = [i for i, b in enumerate(final_blocks) if is_untranslated(b)]
        resolved = len(missed_positions) - len(still_missed)
        print(f"   ✔ Resolved: {resolved} | Still untranslated: {len(still_missed)}")
    else:
        still_missed = [i for i, b in enumerate(final_blocks) if is_untranslated(b)]
        if still_missed:
            print(f"⚠️ Max iterations ({max_iterations}) reached. "
                  f"{len(still_missed)} segment(s) still untranslated.")

    return final_blocks

def main():
    parser = argparse.ArgumentParser(description="Smart Translation with Context & Style")
    parser.add_argument("input", help="Input English SRT file")
    parser.add_argument("--style", default="casual", choices=["casual", "formal", "edgy"])
    parser.add_argument("--model", default="gemini-3-pro", help="Gemini Model (e.g. gemini-3-flash)")
    parser.add_argument("--chunk-size", type=int, default=50, help="Number of blocks per batch")
    
    args = parser.parse_args()
    
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"File not found: {input_path}")
        return

    print(f"🚀 Starting Smart Translation for: {os.path.basename(input_path)}")
    print(f"   Style: {args.style} | Chunk Size: {args.chunk_size}")

    # 1. Parse Input
    blocks = srt_utils.parse_srt(input_path)
    if not blocks:
        print("Error parsing SRT file.")
        return

    total_chunks = math.ceil(len(blocks) / args.chunk_size)
    print(f"   Total Blocks: {len(blocks)} -> {total_chunks} Chunks")

    final_blocks = []
    
    # 2. Process Chunks Concurrenty
    # Prepare all tasks
    tasks = []
    
    # Pre-load rules for efficiency
    verbalizer_snippet = VERBALIZER_RULES[:1500] if VERBALIZER_RULES else "Translate naturally."
    humanizer_snippet = HUMANIZER_RULES[:1500] if HUMANIZER_RULES else "Do not sound robotic."
    knowledge_snippet = ""
    if SUBTRANSLATOR_RULES:
        # Extract Domain Knowledge if present, or just use relevant parts
        match = re.search(r'(## Domain Knowledge & ASR Correction.*)', SUBTRANSLATOR_RULES, re.DOTALL)
        if match:
            knowledge_snippet = match.group(1).strip()
        else:
            # Fallback to general constraints if section not found (or just empty)
            pass
    
    print(f"📦 Preparing {total_chunks} chunks for parallel processing...")
    
    for i in range(total_chunks):
        start = i * args.chunk_size
        end = min((i + 1) * args.chunk_size, len(blocks))
        chunk = blocks[start:end]
        
        # Construct Prompt string here in main loop to be thread-safe/independent
        input_text = ""
        for block in chunk:
            text = " ".join(block['lines']).replace("\n", " ").strip()
            input_text += f"[{block['index']}] {text}\n"
            
        prompt = f"""
You are an expert subtitle translator and editor.
Translate the following English subtitles into Simplified Chinese.

### STEP 1: VERBALIZATION (Tone & Persona)
{verbalizer_snippet}...
TARGET STYLE: {args.style}

### STEP 2: DOMAIN KNOWLEDGE & ASR CORRECTION
{knowledge_snippet}

### STEP 3: HUMANIZATION (De-AI)
{humanizer_snippet}...

### STEP 4: CONTEXT AWARENESS
INPUT BLOCK:
{input_text}

OUTPUT FORMAT:
[ID] Translated Text
...
"""
        tasks.append({
            'index': i,
            'chunk': chunk,
            'prompt': prompt
        })

    # Execute Batch
    try:
        # Use user-specified model, or default to gemini-1.5-flash.
        target_model = args.model
        print(f"🚀 Using LLM: {target_model}...")
        
        results = client.generate_batch(tasks, target_model)
        
        # Sort results by index to ensure correct subtitle order
        results.sort(key=lambda x: x['index'])
        
        for res in results:
            result_text = res.get('result')
            chunk = res['chunk']
            
            translated_chunk_blocks = []
            
            if result_text:
                # Parse output logic
                translated_map = {}
                for line in result_text.split('\n'):
                    match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
                    if match:
                        idx = match.group(1)
                        content = match.group(2).strip()
                        if content:  # guard: reject empty translations
                            translated_map[idx] = content

                # Apply translations; keep original as fallback for missing/empty
                for block in chunk:
                    new_block = block.copy()
                    idx = str(block['index'])
                    if idx in translated_map:
                        new_block['lines'] = [translated_map[idx]]
                    # else: keep original English as fallback (detected by is_untranslated)
                    translated_chunk_blocks.append(new_block)
            else:
                print(f"❌ Chunk {res['index']} failed completely. Will retry in post-processing.")
                translated_chunk_blocks = chunk  # keep original for retry

            final_blocks.extend(translated_chunk_blocks)
            
    except Exception as e:
        print(f"❌ Parallel execution failed: {e}")
        return

    # 3. Post-Processing: retry all untranslated segments
    untranslated_count = sum(1 for b in final_blocks if is_untranslated(b))
    if untranslated_count > 0:
        print(f"\n🔍 Post-processing: {untranslated_count} untranslated segment(s) found. Starting retry loop...")
        final_blocks = postprocess_retry_loop(
            final_blocks, client, target_model, args.style,
            verbalizer_snippet, humanizer_snippet, knowledge_snippet
        )
    else:
        print("\n✅ All segments translated on first pass. Skipping post-processing.", flush=True)

    # 4. Final Style-Guide Humanization (single pass over all blocks)
    print("\n✨ Applying style guide and humanization to all blocks...")
    for block in final_blocks:
        block['lines'] = [humanize_text(l) for l in block['lines']]

    # 5. Save Output
    if input_path.lower().endswith(".en.srt"):
        output_path = input_path[:-7] + ".cn.srt"
    else:
        output_path = input_path.replace(".srt", ".cn.srt")

    if os.path.exists(output_path):
        base, ext = os.path.splitext(output_path)
        output_path = f"{base}_smart{ext}"

    srt_utils.write_srt(final_blocks, output_path)
    print(f"✅ Translation Saved to: {output_path}", flush=True)

if __name__ == "__main__":
    main()
