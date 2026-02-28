
# AutoSub: 全自动视频字幕生成工具

AutoSub 是一款专业的“零点击”自动化工具，旨在实现视频下载、语音识别、智能翻译及字幕压制的一体化流程。它既可以作为独立工具使用，也可以作为 AI 智能体（如 Antigravity, CC, 或 Codex）的扩展技能（Skill）。

## ✨ 功能特性
- **智能下载**：自动抓取来自 YouTube, Twitter, Bilibili 等平台的视频。
- **Whisper 转录**：基于 `faster-whisper` 实现高精度的英文语音转识别。
- **LLM 智能翻译**：利用 Gemini (Flash/Pro), 智谱 (GLM), 或 OpenAI 进行上下文感知翻译，并内置“去 AI 味”的人性化润色规则。
- **专业字幕压制**：一键生成带有双语布局和专业样式盒（Vector-Box）的硬字幕视频。
- **动态模型探测**：自动发现并列出各厂商最新的 AI 模型。
- **图形界面与命令行**：提供直观的 GUI 界面及强大的 CLI 自动化支持。

## 🚀 一键安装 (Windows)

1. **下载或克隆** 本代码库到本地。
2. **右键点击** `install.ps1` 脚本，选择 **“使用 PowerShell 运行”**。
   - *该脚本会自动检查并安装 Python 3.12、FFmpeg 以及所有必要的 Python 库。*
3. **配置 API 密钥**：
   - **方法 A (最简单)**：启动图形界面 (`autosub_gui.py`)，在 "API Key" 输入框填入密钥并点击 **“保存该密钥”**。程序会自动为您创建 `.env` 文件。
   - **方法 B (手动)**：在根目录下创建 `.env` 文件并添加：
     - `ZHIPUAI_API_KEY=您的密钥` (推荐使用智谱，支持免费模型)
     - `GEMINI_API_KEY=您的密钥`
     - `OPENAI_API_KEY=您的密钥`

## 📖 使用方法

### 1. 图形界面模式 (推荐)
运行以下命令启动：
```powershell
python Library\Tools\autosub\autosub_gui.py
```

### 2. Cookies 配置 (获取受限视频)
如果遇到 YouTube 机器人验证（Bot Detection）或处理 Bilibili 会员专享视频，需配置 Cookies：
1. 在浏览器安装扩展：[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmclabimipcebeociikabmgepmeadon) 或 **EditThisCookie**。
2. 访问对应的视频网站并登录。
3. 点击扩展，导出为 **Netscape 格式** 的 `cookies.txt`。
4. **使用方法**：
   - **GUI**：在“Cookies”栏点击“选择...”，加载该文件。
   - **CLI**：在命令后添加 `--cookies "path/to/cookies.txt"`。

### 3. AI 智能体模式 (IDE / 工作区)
如果您正在使用支持智能体的工作空间（如 Antigravity 或 CC），只需输入：
> `/autosub`

智能体会自动读取 `.agent/workflows/autosub.md` 中的工作流逻辑并引导您完成处理。

## 🛠️ 项目结构
- `.agent/workflows/`：存放供 AI 智能体使用的自动化工作流定义。
- `Library/Tools/`：
  - `autosub/`：主逻辑程序及图形界面。
  - `vdown/`：视频下载引擎（基于 yt-dlp）。
  - `transcriber/`：语音转文字引擎（Whisper）。
  - `subtranslator/`：翻译逻辑及 SRT 工具集。
  - `hardsubber/`：ASS 转换及 FFmpeg 压制引擎。
  - `common/`：共享工具组件。

## 📄 许可证
MIT License。欢迎自由分享、修改和使用！
