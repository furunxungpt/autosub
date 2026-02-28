import sys
import os
import datetime
import subprocess
import re
import time
from pathlib import Path

# --- Configuration ---
# Find working executables
PYTHON_EXE = sys.executable
# Target specifically the one we verified
YTDLP_EXE = r"C:\Program Files\Python\Python312\Scripts\yt-dlp.exe"
if not os.path.exists(YTDLP_EXE):
    # Fallback search
    import shutil
    YTDLP_EXE = shutil.which("yt-dlp") or "yt-dlp"

NODE_EXE = "node"
possible_node_paths = [
    r"C:\Program Files\nodejs",
    r"D:\Program Files\nodejs",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"),
]
for p in possible_node_paths:
    exe = os.path.join(p, "node.exe")
    if os.path.exists(exe):
        NODE_EXE = exe
        break

if getattr(sys, 'frozen', False):
    DOWNLOAD_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "AutoSub", "Downloads")
else:
    DOWNLOAD_ROOT = r"d:\cc\download"

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def get_progress_from_line(line):
    # Match "[download]  12.3% of" or "[download] 100%"
    match = re.search(r'\[download\]\s+(\d+\.?\d*)%', line)
    if match:
        return match.group(1)
    return None

def download_video(url, custom_cookies=None, out_dir=None):
    if out_dir:
        target_dir = out_dir
    else:
        target_dir = DOWNLOAD_ROOT

    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    log(f"🎬 Starting download via CLI...")
    log(f"   URL: {url}")
    log(f"   Output: {target_dir}")

    # Build Command
    cmd = [
        YTDLP_EXE,
        "--js-runtimes", f"node:{NODE_EXE}",
        "--remote-components", "ejs:github",
        "--no-playlist",
        "--progress",
        "--newline",
        "--merge-output-format", "mp4",
        "-o", os.path.join(target_dir, "%(title)s [%(id)s] [%(height)sp].%(ext)s")
    ]

    # Handle cookies
    cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    if custom_cookies and os.path.exists(custom_cookies):
        log(f"Using custom cookies: {custom_cookies}")
        cmd.extend(["--cookies", custom_cookies])
    elif os.path.exists(cookies_file):
        cmd.extend(["--cookies", cookies_file])

    cmd.append(url)

    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8', 
            errors='replace',
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )

        for line in process.stdout:
            line = line.strip()
            if not line: continue
            
            p = get_progress_from_line(line)
            if p:
                print(f"Progress: {p}%", flush=True)
            else:
                # Still show other logs for context
                if "[youtube]" in line or "[info]" in line or "ERROR" in line or "WARNING" in line:
                    print(line, flush=True)

        process.wait()
        if process.returncode == 0:
            log("✅ Download completed successfully.")
            return True
        else:
            log(f"❌ Download failed with exit code {process.returncode}")
            return False

    except Exception as e:
        log(f"❌ Error launching yt-dlp: {e}")
        return False

def get_title(url, cookies=None):
    cmd = [
        YTDLP_EXE,
        "--js-runtimes", f"node:{NODE_EXE}",
        "--remote-components", "ejs:github",
        "--get-title",
        "--no-playlist"
    ]
    if cookies and os.path.exists(cookies):
        cmd.extend(["--cookies", cookies])
    
    cmd.append(url)
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except: pass
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download.py <URL> [cookies_file] [out_dir]")
        sys.exit(1)
    
    video_url = sys.argv[1]
    cookies_arg = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else None
    out_dir_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3].strip() else None
    
    if "--get-title" in sys.argv:
        title = get_title(video_url, cookies_arg)
        if title:
            print(title)
            sys.exit(0)
        else:
            print("Error: Could not fetch title")
            sys.exit(1)

    success = download_video(video_url, cookies_arg, out_dir_arg)
    if not success:
        sys.exit(1)
