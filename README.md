
# AutoSub: End-to-End Automated Subtitling

[English](README.md) | [简体中文](README_ZH.md)

AutoSub is a professional, "zero-click" workflow to download, transcribe, translate, and hardburn subtitles for any video. It is designed to be used both as a standalone tool and as an extension (Skill) for AI Agents (like Antigravity, CC, or Codex).

## ✨ Features
- **Smart Download**: Automatically fetches videos from YouTube, Twitter, Bilibili, etc.
- **Whisper Transcription**: Uses `faster-whisper` for high-accuracy English transcription.
- **LLM Translation**: Context-aware translation using Gemini (Flash/Pro), Zhipu (GLM), or OpenAI, with humanized style rules.
- **Professional Styling**: One-click generation of hard-subbed videos with bilingual layouts and vector-box styles.
- **Dynamic Model Discovery**: Automatically discovers the latest models from API providers.
- **GUI & CLI**: User-friendly interface or powerful command-line automation.

## 🚀 One-Click Installation (Windows)

1. **Clone or Download** this repository to your computer.
2. **Right-click** `install.ps1` and select **"Run with PowerShell"**.
   - *This script will automatically install Python 3.12, FFmpeg, and all required Python libraries.*
3. **Configure API Key**:
   - **Method A (Easiest)**: Run the GUI (`autosub_gui.py`), enter your key in the "API Key" field, and click **"Save Key"**. The `.env` file will be created automatically.
   - **Method B (Manual)**: Create a `.env` file in the root directory and add:
     - `ZHIPUAI_API_KEY=your_key` (Recommended: Free tier supported)
     - `GEMINI_API_KEY=your_key`
     - `OPENAI_API_KEY=your_key`

## 📖 How to Use

### 1. GUI Mode (Recommended)
Run the following command:
```powershell
python Library\Tools\autosub\autosub_gui.py
```

### 2. Cookie Configuration (For Restricted Videos)
If you encounter YouTube bot detection or need to download Bilibili premium content, you must provide cookies:
1. Install a browser extension: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmclabimipcebeociikabmgepmeadon) or **EditThisCookie**.
2. Log in to the target video site.
3. Click the extension and export cookies in **Netscape format** as `cookies.txt`.
4. **Usage**:
   - **GUI**: Click "Browse..." in the "Cookies" row to load the file.
   - **CLI**: Append `--cookies "path/to/cookies.txt"` to your command.

### 3. AI Agent Mode (IDE / Workspace)
If you are using an AI Agent (like Antigravity or CC), you can simply type:
> `/autosub`

The agent will read the workflow in `.agent/workflows/autosub.md` and guide you through the process.

## 🛠️ Project Structure
- `.agent/workflows/`: Contains the workflow definition for AI Agents.
- `Library/Tools/`:
  - `autosub/`: Main logic and GUI.
  - `vdown/`: Video download engine (yt-dlp based).
  - `transcriber/`: Transcription engine (Whisper).
  - `subtranslator/`: Translation & SRT utilities.
  - `hardsubber/`: ASS conversion and FFmpeg burning.
  - `common/`: Shared utility sets.

## 📄 License
MIT License. Feel free to share and modify!
