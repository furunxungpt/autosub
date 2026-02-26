
import os
import sys
import argparse
import subprocess
import glob
import time
import re
import shutil
import json
import io

# System and Third-party imports

# Force UTF-8 for stdout/stderr to handle emojis in logs on Windows
if sys.platform == "win32":
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass

# --- Logging Helper ---
class Logger:
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, "a", encoding="utf-8", errors="replace")
        
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.terminal.flush()
        self.log_file.flush()
        
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None

# --- Configuration ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULTS_FILE = os.path.join(CURRENT_DIR, "defaults.json")
DEFAULTS = {}
if os.path.exists(DEFAULTS_FILE):
    try:
        with open(DEFAULTS_FILE, "r", encoding="utf-8") as f:
            DEFAULTS = json.load(f)
    except: pass

import multiprocessing
multiprocessing.freeze_support()

# --- Environment Setup (Isolation Logic) ---
if getattr(sys, 'frozen', False):
    # Packaged / Installer Mode
    BUNDLE_DIR = sys._MEIPASS
    TOOLS_DIR = os.path.join(BUNDLE_DIR, "Library", "Tools")
    USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "AutoSub")
    PROJECT_ROOT = USER_DATA_DIR
    BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Projects")
    env_path = os.path.join(PROJECT_ROOT, ".env")
    
    # In bundled mode, common is in BUNDLE_DIR/Library/Tools/common
    sys.path.append(os.path.join(TOOLS_DIR, "common"))
else:
    # Developer Mode (d:\cc)
    CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    TOOLS_DIR = os.path.dirname(CURRENT_SCRIPT_DIR)
    
    # Anchor to true repository root d:\cc
    tmp_root = os.path.dirname(TOOLS_DIR)
    if os.path.basename(tmp_root).lower() == "library":
        PROJECT_ROOT = os.path.dirname(tmp_root)
    else:
        PROJECT_ROOT = tmp_root
        
    BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Projects")
    env_path = os.path.join(PROJECT_ROOT, ".env")
    
    # In dev mode, common is in d:\cc\Library\Tools\common
    sys.path.append(os.path.join(TOOLS_DIR, "common"))
    print(f"🏠 [DEV MODE] Root: {PROJECT_ROOT}")

# Load srt_utils after path setup
try:
    import srt_utils
except ImportError:
    srt_utils = None

# --- Robust FFmpeg/ffprobe Detection ---
def find_tool(tool_name):
    """Finds a tool in PATH or common installation directories."""
    import shutil
    # 0. Check bundled internal path (if frozen)
    if getattr(sys, 'frozen', False):
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        internal_tool = os.path.join(bundle_dir, tool_name + ".exe")
        if os.path.exists(internal_tool): return internal_tool
        # Also check root of exe
        root_tool = os.path.join(os.path.dirname(sys.executable), tool_name + ".exe")
        if os.path.exists(root_tool): return root_tool

    # 1. Check PATH
    path = shutil.which(tool_name)
    if path: return path
    
    # 2. Check WinGet Gyan FFmpeg (User Specific)
    user_home = os.path.expanduser("~")
    winget_base = os.path.join(user_home, "AppData", "Local", "Microsoft", "Winget", "Packages")
    if os.path.exists(winget_base):
        # Search for Gyan FFmpeg
        for d in os.listdir(winget_base):
            if "Gyan.FFmpeg" in d:
                # Glob search for the bin folder
                for bin_dir in glob.glob(os.path.join(winget_base, d, "**/bin"), recursive=True):
                    tool_path = os.path.join(bin_dir, tool_name + ".exe")
                    if os.path.exists(tool_path): return tool_path

    # 3. Check common hardcoded paths
    fallbacks = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    
    # Proactively check for CapCut installation to steal its FFmpeg
    # Better: check for "CapCut.exe" path and then look for ffmpeg nearby
    for drive in ["C:", "D:"]:
        capcut_root = os.path.join(drive, "Program Files", "CapCut")
        if os.path.exists(capcut_root):
            # Find latest version folder
            try:
                versions = [d for d in os.listdir(capcut_root) if os.path.isdir(os.path.join(capcut_root, d)) and "." in d]
                if versions:
                    latest = sorted(versions, key=lambda x: [int(v) for v in x.split('.') if v.isdigit()], reverse=True)[0]
                    fallbacks.append(os.path.join(capcut_root, latest))
            except: pass

    for fb in fallbacks:
        tool_path = os.path.join(fb, tool_name + ".exe")
        if os.path.exists(tool_path): return tool_path
        
    return tool_name # Fallback to original name and hope for the best

FFMPEG_EXE = find_tool("ffmpeg")
FFPROBE_EXE = find_tool("ffprobe")

if FFMPEG_EXE != "ffmpeg":
    print(f"📦 Found FFmpeg at: {FFMPEG_EXE}")
    # Add to path for sub-scripts
    os.environ["PATH"] += os.pathsep + os.path.dirname(FFMPEG_EXE)

VDOWN_CMD = [sys.executable, os.path.join(TOOLS_DIR, "vdown", "download.py")]
TRANSCRIBER_CMD = [sys.executable, os.path.join(TOOLS_DIR, "transcriber", "transcribe_engine.py"), "run"]
SMART_TRANSLATE_CMD = [sys.executable, os.path.join(TOOLS_DIR, "autosub", "smart_translate.py")]
SUBTRANSLATOR_CMD = [sys.executable, os.path.join(TOOLS_DIR, "subtranslator", "subtranslator.py")]
SRT2ASS_CMD = [sys.executable, os.path.join(TOOLS_DIR, "hardsubber", "srt_to_ass.py")]
BURNSUB_CMD = [sys.executable, os.path.join(TOOLS_DIR, "hardsubber", "burn_engine.py")]

if os.path.exists(env_path):
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f :
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    if k and v: os.environ[k] = v.strip('"\'')
    except: pass

def get_workdir(input_val):
    if input_val.startswith("http"):
        return os.path.join(BASE_OUTPUT_DIR, "temp_" + str(int(time.time())))
    else:
        abs_path = os.path.abspath(input_val)
        try:
            base = os.path.normpath(BASE_OUTPUT_DIR).lower()
            current = os.path.normpath(abs_path).lower()
            if current.startswith(base): return os.path.dirname(abs_path)
        except: pass
        return os.path.join(BASE_OUTPUT_DIR, os.path.splitext(os.path.basename(input_val))[0])

def get_video_title(url, cookies=None):
    """Fetches video title using download.py --get-title."""
    try:
        cmd = list(VDOWN_CMD) + [url, cookies or "", "", "--get-title"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            title = result.stdout.strip()
            if title and "Error" not in title:
                return title
    except: pass
    return None

def sanitize_filename(filename):
    """Cleans a string to be a safe filename."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', filename)
    clean = clean.strip().strip('.') # Strip trailing spaces and dots
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:100] # Limit length

def download_video(url, workdir, cookies=None):
    print(f"🎬 Downloading {url}...", flush=True)
    if not os.path.exists(workdir): os.makedirs(workdir)
    cmd = list(VDOWN_CMD) + [url, cookies or "", workdir]
    try: 
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        for line in process.stdout:
            print(line.strip(), flush=True)
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
    except subprocess.CalledProcessError as e:
        print(f"❌ Download command failed with code {e.returncode}")
        print("💡 Tip: If you see 'Sign in to confirm you’re not a bot', try providing a cookies file using --cookies.")
        return None
    except Exception as e:
        print(f"❌ Error launching download: {e}")
        return None
        
    vids = [f for f in glob.glob(os.path.join(workdir, "*")) if os.path.splitext(f)[1].lower() in ['.mp4', '.mkv', '.webm', '.ts', '.mov', '.avi']]
    if not vids:
        print(f"❌ No video files found in {workdir} after download attempt.")
        return None
        
    return max(vids, key=os.path.getmtime)

def transcribe_video(video_path, workdir, model="large-v3-turbo"):
    print(f"🎙️ Transcribing {os.path.basename(video_path)}...", flush=True)
    cmd = list(TRANSCRIBER_CMD) + [video_path, "--model", model, "--output", workdir, "--no-gui"]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        for line in process.stdout:
            print(line.strip(), flush=True)
        process.wait()
        res = os.path.join(workdir, os.path.splitext(os.path.basename(video_path))[0] + ".srt")
        if os.path.exists(res):
            en_res = res.replace(".srt", ".en.srt")
            if not os.path.exists(en_res):
                shutil.copy2(res, en_res)
                print(f"✅ Created copy: {os.path.basename(en_res)}")
            return res
        return None
    except: return None

def merge_bilingual(src_srt, zh_srt, main_lang="cn", llm_model="gemini-3.1-pro-preview"):
    print(f"🔀 Smart-Merging into bilingual SRT...")
    bi_path = src_srt[:-7] + ".bi.srt" if src_srt.lower().endswith(".en.srt") else src_srt.replace(".srt", ".bi.srt")
    
    # Check if a healthy bi_path already exists
    if os.path.exists(bi_path) and os.path.getsize(bi_path) > 100:
        with open(bi_path, 'r', encoding='utf-8', errors='ignore') as f:
            if "[UNTRANSLATED]" not in f.read(): 
                print(f"✅ Reusing existing bilingual file: {os.path.basename(bi_path)}")
                return bi_path
            
    cmd = list(SUBTRANSLATOR_CMD) + ["merge", src_srt, "--translated-file", zh_srt]
    env = os.environ.copy(); env["GEMINI_MODEL"] = llm_model
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', env=env)
        for line in process.stdout:
            msg = line.strip()
            if "Progress:" in msg:
                print(msg, flush=True)
            else:
                print(f"   [Merge] {msg}", flush=True)
        process.wait()
        
        if process.returncode == 0 and os.path.exists(bi_path):
            return bi_path
        else:
            print(f"❌ Merge process failed with code {process.returncode}")
            return None
    except Exception as e:
        print(f"❌ Merge launch error: {e}")
        return None

def burn_subtitle(video_path, srt_path, layout, main_lang, cn_font, en_font, cn_size, en_size, cn_color, en_color, bg_box=True):
    print("🔥 Burning subtitles...", flush=True)
    base_srt, _ = os.path.splitext(srt_path)
    ass_path = base_srt + ".ass"
    
    # --- Get Video Dimensions for Styling ---
    width, height = get_video_dimensions(video_path)
    print(f"📐 Video Resolution: {width}x{height}")

    if not os.path.exists(ass_path):
        cmd = list(SRT2ASS_CMD) + [srt_path, ass_path, "--layout", layout, "--main-lang", main_lang, "--cn-font", cn_font, "--en-font", en_font, "--cn-size", cn_size, "--en-size", en_size, "--cn-color", cn_color, "--en-color", en_color]
        cmd += ["--width", str(width), "--height", str(height)]
        if not bg_box: cmd.append("--no-bg-box")
        subprocess.run(cmd, check=True)
        
    video_base = os.path.splitext(os.path.basename(video_path))[0]
    video_ext = os.path.splitext(video_path)[1]
    out_video = os.path.join(os.path.dirname(srt_path), video_base + "_hardsub" + video_ext)
    
    # --- Critical: Prevent File Locking issues ---
    if os.path.exists(out_video):
        try:
            os.remove(out_video)
        except PermissionError:
            print(f"❌ Error: Output file is LOCKED: {os.path.basename(out_video)}")
            print(f"   Please close any video players or run: Stop-Process -Name ffmpeg -Force")
            return None
        except Exception as e:
            print(f"⚠️ Warning: Could not remove existing output: {e}")

    cmd = list(BURNSUB_CMD) + [video_path, ass_path, out_video, "--headless"]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        last_logs = []
        for line in process.stdout:
            msg = line.strip()
            if msg:
                # If it's a progress line, don't prefix it so it's cleaner for the GUI regex
                if "Progress:" in msg:
                    print(msg, flush=True)
                else:
                    print(f"   [Burn] {msg}", flush=True)
                last_logs.append(msg)
                if len(last_logs) > 50: last_logs.pop(0)
        
        process.wait()
        if process.returncode != 0:
            print(f"❌ Burn failed with exit code {process.returncode}")
            # If logs didn't print or were short, show them again
            if not last_logs: print("   No log output captured.")
            raise subprocess.CalledProcessError(process.returncode, cmd)
            
    except Exception as e:
        if isinstance(e, subprocess.CalledProcessError): raise e
        print(f"❌ Launch Error: {e}")
        return None
    return out_video if os.path.exists(out_video) else None

def get_video_duration(path):
    try:
        cmd = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        return float(subprocess.check_output(cmd).decode().strip())
    except: return 0

def get_video_dimensions(path):
    """Returns (width, height) using ffprobe."""
    try:
        cmd = [FFPROBE_EXE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path]
        out = subprocess.check_output(cmd).decode().strip()
        if "x" in out:
            w, h = out.split("x")
            return int(w), int(h)
    except: pass
    return 1920, 1080

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--llm-model", default="gemini-1.5-flash", help="LLM Model (gemini-1.5-flash, gpt-4o, moonshot-v1-8k, qwen-plus, glm-4, etc.)")
    parser.add_argument("--style", default="casual")
    parser.add_argument("--cookies")
    parser.add_argument("--layout", default="bilingual")
    parser.add_argument("--main-lang", default="cn")
    parser.add_argument("--cn-font", default="KaiTi")
    parser.add_argument("--en-font", default="Arial")
    parser.add_argument("--cn-size", default="60")
    parser.add_argument("--en-size", default="36")
    parser.add_argument("--cn-color", default="Gold")
    parser.add_argument("--en-color", default="White")
    parser.add_argument("--no-bg-box", action="store_true")
    args = parser.parse_args()

    # 0. Intelligent Project Naming
    if args.input.startswith("http"):
        print(f"🔍 Fetching video details...")
        title = get_video_title(args.input, args.cookies)
        if title:
            safe_title = sanitize_filename(title)
            workdir = os.path.join(BASE_OUTPUT_DIR, safe_title)
            print(f"📁 Project Folder: {safe_title}")
        else:
            workdir = get_workdir(args.input)
    else:
        workdir = get_workdir(args.input)

    if not os.path.exists(workdir): os.makedirs(workdir)
    
    # --- Initialize Workflow Logging ---
    log_path = os.path.join(workdir, "workflow.log")
    logger = Logger(log_path)
    sys.stdout = logger
    sys.stderr = logger

    print(f"--- 任务启动: {args.input} ---")
    print(f"🏠 [DEV MODE] Root: {PROJECT_ROOT}")
    print(f"📦 Found FFmpeg at: {FFMPEG_EXE}")

    if args.input.startswith("http"):
        video_path = download_video(args.input, workdir, args.cookies)
    else:
        # For local files, copy them to workdir to keep project self-contained
        src_path = os.path.abspath(args.input)
        dest_path = os.path.join(workdir, os.path.basename(src_path))
        if os.path.exists(src_path):
            if os.path.abspath(src_path).lower() != os.path.abspath(dest_path).lower():
                print(f"📂 Copying video to project folder...")
                shutil.copy2(src_path, dest_path)
            video_path = dest_path
        elif os.path.exists(dest_path):
            print(f"ℹ️ Original source missing, using video in project folder.")
            video_path = dest_path
        else:
            video_path = src_path # Will fail below
            
    if not video_path or not os.path.exists(video_path): return print("❌ Invalid input")

    vid_dur = get_video_duration(video_path)
    base = os.path.splitext(os.path.basename(video_path))[0]
    expected_srt = os.path.join(workdir, base + ".srt")
    expected_en = os.path.join(workdir, base + ".en.srt")
    expected_cn = os.path.join(workdir, base + ".cn.srt")

    # 1. Transcription (Sequential)
    src_srt = None
    
    # Priority: 1. .srt (Transcribed) 2. .en.srt (Downloaded)
    possible_sources = [expected_srt, expected_en]
    
    for candidate in possible_sources:
        if os.path.exists(candidate) and os.path.getsize(candidate) > 500:
            if srt_utils:
                if vid_dur > 0:
                    try:
                        srt_dur = srt_utils.get_srt_duration(candidate)
                        if srt_dur > vid_dur * 0.9:
                            print(f"✅ Found existing SRT: {os.path.basename(candidate)} (Duration matches)")
                            src_srt = candidate
                            break
                        else:
                            print(f"⚠️ {os.path.basename(candidate)} duration mismatch ({srt_dur:.1f}s vs {vid_dur:.1f}s).")
                    except Exception as e:
                        print(f"⚠️ Error checking {os.path.basename(candidate)}: {e}")
                else:
                    print(f"✅ Found existing SRT: {os.path.basename(candidate)} (Video duration unknown, skipping transcription)")
                    src_srt = candidate
                    break
            else:
                # If srt_utils is missing, we still trust the file if it's > 500 bytes
                print(f"✅ Found existing SRT: {os.path.basename(candidate)} (srt_utils missing, assuming OK)")
                src_srt = candidate
                break
    
    if not src_srt:
        src_srt = transcribe_video(video_path, workdir, args.model)
    
    if not src_srt: return print("❌ Transcription failed")

    # 2. Translation (Sequential)
    zh_srt = None
    expected_zh = os.path.join(workdir, base + ".zh.srt")
    
    for candidate_cn in [expected_cn, expected_zh]:
        if os.path.exists(candidate_cn) and os.path.getsize(candidate_cn) > 500:
            if srt_utils:
                try:
                    src_count = len(srt_utils.parse_srt(src_srt))
                    zh_count = len(srt_utils.parse_srt(candidate_cn))
                    if zh_count >= src_count * 0.95:
                        print(f"✅ Found existing translation: {os.path.basename(candidate_cn)}")
                        zh_srt = candidate_cn
                        break
                except Exception as e:
                    print(f"⚠️ Error parsing {os.path.basename(candidate_cn)}: {e}")
            else:
                zh_srt = candidate_cn
                break

    if not zh_srt:
        print("🌍 Smart-translating...")
        try:
            cmd = list(SMART_TRANSLATE_CMD) + [src_srt, "--style", args.style, "--model", args.llm_model]
            subprocess.run(cmd, check=True)
            if os.path.exists(expected_cn): zh_srt = expected_cn
            elif os.path.exists(expected_zh): zh_srt = expected_zh
        except Exception as e:
            print(f"⚠️ Translation step error: {e}")
    
    if not zh_srt: return print("❌ Translation failed")

    # 3. Merge & Burn
    final_srt = zh_srt
    if args.layout == "bilingual":
        print(f"🔀 Merging {os.path.basename(src_srt)} and {os.path.basename(zh_srt)}...")
        merged = merge_bilingual(src_srt, zh_srt, args.main_lang, args.llm_model)
        if merged and os.path.exists(merged):
            final_srt = merged
        else:
            # Check if there's an existing .bi.srt anyway (maybe created but returned None due to error code)
            bi_path = src_srt[:-7] + ".bi.srt" if src_srt.lower().endswith(".en.srt") else src_srt.replace(".srt", ".bi.srt")
            if os.path.exists(bi_path) and os.path.getsize(bi_path) > 500:
                print(f"✅ Using legacy/existing bilingual file: {os.path.basename(bi_path)}")
                final_srt = bi_path
            else:
                print(f"⚠️ Bilingual merge failed. Falling back to primary translation: {os.path.basename(zh_srt)}")
                final_srt = zh_srt
    
    print(f"📍 Final subtitle for burning: {os.path.basename(final_srt)}", flush=True)
    burn_subtitle(video_path, final_srt, args.layout, args.main_lang, args.cn_font, args.en_font, args.cn_size, args.en_size, args.cn_color, args.en_color, not args.no_bg_box)
    print("✅ All done!", flush=True)

if __name__ == "__main__":
    main()
