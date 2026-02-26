import sys
import os
import datetime
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("❌ Error: yt-dlp not installed")
    print("Please install: pip install yt-dlp")
    sys.exit(1)

# Add node path
node_path = r"C:\Program Files\nodejs"
if node_path not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + node_path

import io

# Force UTF-8 for stdout/stderr to handle emojis in logs on Windows
if sys.platform == "win32":
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass

try:
    import gartner
except ImportError:
    gartner = None

if getattr(sys, 'frozen', False):
    DOWNLOAD_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "AutoSub", "Downloads")
else:
    DOWNLOAD_ROOT = r"D:\0000\download"

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def download_video(url, custom_cookies=None, output_dir=None):
    global DOWNLOAD_ROOT
    if output_dir:
        DOWNLOAD_ROOT = output_dir
    # Early detection: Check if URL is already a direct stream
    is_direct_stream = any([
        '.m3u8' in url,
        '.mp4' in url,
        'stream.mux.com' in url,
        'stream-ext.bizzabo.com' in url,
        'manifest-gcp' in url
    ])
    
    if is_direct_stream:
        log("Detected direct stream URL. Skipping extraction...")
        # Note: direct streams might need ffmpeg or direct download, but yt-dlp usually handles them too.
        # We will pass them to yt-dlp as well, as it is robust.
        
    elif "gartner.com" in url and gartner:
        log("Detected Gartner webinar URL. Trying API extraction...")
        event_id, session_id = gartner.get_session_details_from_url(url)
        if event_id and session_id:
            mux_url = gartner.fetch_mux_url(event_id, session_id, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"))
            if mux_url:
                log(f"API extraction successful: {mux_url}")
                url = mux_url
            else:
                log("API extraction failed. Please use manual extraction or check cookies.")
                return
        else:
            log("Could not parse Gartner event details from URL.")
            return

    # Ensure the download directory exists
    if not os.path.exists(DOWNLOAD_ROOT):
        try:
            os.makedirs(DOWNLOAD_ROOT)
            log(f"Created download directory: {DOWNLOAD_ROOT}")
        except OSError as e:
            log(f"Error creating directory {DOWNLOAD_ROOT}: {e}")
            return
            
    log(f"🎬 Starting download...")
    log(f"   URL: {url}")
    log(f"   Output: {DOWNLOAD_ROOT}")

    def progress_hook(d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%','')
            try:
                # Standardize to "Progress: X.X%" for GUI matching
                print(f"Progress: {p}%", flush=True)
            except: pass
        elif d['status'] == 'finished':
            print("Progress: 100.0%", flush=True)

    # yt-dlp configuration
    ydl_opts = {
        # Video format: Absolute best video and audio merged
        'format': 'bestvideo+bestaudio/best',
        # Remux to mp4 at the end for consistency and compatibility
        'merge_output_format': 'mp4',
        # Do not restrict extension preference to allow highest bitrate streams (e.g. VP9/AV1)
        'format_sort': ['res', 'br', 'size'],
        
        # Output template
        'outtmpl': os.path.join(DOWNLOAD_ROOT, '%(title)s [%(id)s] [%(height)sp].%(ext)s'),
        
        # Subtitles
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        
        # Metadata
        'writethumbnail': False,
        
        # Verbosity
        'quiet': False,
        'no_warnings': False,
        
        'js_runtime': 'node',
        'progress_hooks': [progress_hook],
    }
    
    # Optional: If FFmpeg is not in PATH, we could add a search here, 
    # but yt-dlp is usually smart enough if it's in a standard place.
    
    # Handle cookies
    cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    if custom_cookies and os.path.exists(custom_cookies):
        log(f"Using custom cookies: {custom_cookies}")
        ydl_opts['cookiefile'] = custom_cookies
    elif os.path.exists(cookies_file):
        # Only use default cookies.txt if it exists
        # log(f"Using cookies.txt from {cookies_file}")
        ydl_opts['cookiefile'] = cookies_file
        
    # Function to execute download with given options
    def execute_download(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Unknown')
            log(f"✅ Download completed: {video_title}")
            return True

    try:
        # First attempt (with cookies if available)
        log("Attempting download...")
        execute_download(ydl_opts)
        return True
            
    except Exception as e:
        error_msg = str(e)
        log(f"❌ Attempt 1 failed: {error_msg}")
        
        # Check if we used cookies and arguably should try without them
        if 'cookiefile' in ydl_opts:
            log("⚠️  Download with cookies failed. Retrying WITHOUT cookies...")
            del ydl_opts['cookiefile']
            try:
                execute_download(ydl_opts)
                return True
            except Exception as e2:
                log(f"❌ Retry failed: {str(e2)}")
                return False
        else:
            return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download.py <URL> [cookies_file] [out_dir]")
        sys.exit(1)
    
    video_url = sys.argv[1]
    cookies_arg = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else None
    out_dir_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3].strip() else None
    
    if "--get-title" in sys.argv:
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True}
            if cookies_arg and os.path.exists(cookies_arg):
                ydl_opts['cookiefile'] = cookies_arg
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                print(info.get('title', 'Unknown'))
                sys.exit(0)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    if out_dir_arg:
        DOWNLOAD_ROOT = out_dir_arg
        
    success = download_video(video_url, cookies_arg)
    if not success:
        sys.exit(1)
