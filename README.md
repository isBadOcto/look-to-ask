# Look to Ask

**Look at anything, ask anything.**

An open-source Windows desktop MVP that combines webcam gaze tracking, an explicitly triggered screenshot, and a typed or spoken question. Look at text, an image or an error, hold a shortcut to speak, and read the answer in Codex or the API answer window.

Current local version: **0.5.0**. Interface languages: **English and Simplified Chinese**. EyeTrax is the sole gaze backend. The owner has exercised the core workflows and GPU speech experience. Webcam accuracy still depends on the person and setup; automated tests do not prove human accuracy or AI answer correctness.

## Demo

[![Watch the Look to Ask demo on YouTube](https://i.ytimg.com/vi/1-aavihZx8s/hqdefault.jpg)](https://www.youtube.com/watch?v=1-aavihZx8s)

[Watch the 1-minute demo on YouTube](https://www.youtube.com/watch?v=1-aavihZx8s).

## Install

This repository currently provides source code. To run it now, follow [Develop and build](#develop-and-build) from a source checkout. The artifact names below refer to local builds, not published download links.

Requires Windows 10/11 x64, a webcam, a microphone for voice, and either a compatible installed Codex desktop app or an OpenAI-compatible multimodal API. The installer needs neither Python nor a GPU. Windows 11 is the tested development platform; clean Windows 10 remains unverified.

Prerequisite: Windows 10/11 x64 and [Microsoft Visual C++ v14 x64 Runtime](https://aka.ms/vc14/vc_redist.x64.exe) **14.51.36247 or newer**. Installing this Microsoft prerequisite may require administrator permission. The installer checks it and explains what is missing. Portable users must install it too.

- `dist/LookToAsk-0.5.0-Setup.exe`: current-user installation, Start menu entry and uninstaller; the application installs without administrator rights once its Microsoft runtime prerequisite is present.
- `dist/LookToAsk-0.5.0-Windows-x64.zip`: portable version. Extract the whole folder and run `LookToAsk.exe`; keep `_internal` beside it.
- `dist/LookToAsk-0.5.0-Source.zip`: source, tests, documentation and dependency declarations.
- `dist/LookToAsk-0.5.0-LibrarySources.zip`: corresponding LGPL library sources and build/replacement instructions; keep this with binary deliveries.
- `dist/SHA256SUMS.txt`: SHA-256 checksums.

These are local build artifacts. **No GitHub Release has been published.** The application is unsigned; Windows may display an unknown-publisher warning.

The standard binary includes proprietary Intel OpenMP/oneMKL components under their separate terms. The installer presents these component-specific terms; portable users should read `_internal/LICENSES/Intel-Runtime-Terms.txt` before use. Qt/FFmpeg LGPL modification and debugging rights are preserved. Deliver both source ZIPs with binaries.

First gaze preparation downloads a generic MediaPipe model, about 4 MB. Speech defaults to multilingual Whisper `medium`, about 1.5 GB; `small`, about 490 MB, is faster on CPU. Models are cached locally and are not bundled. Preparation needs Internet access initially; gaze and speech recognition then run locally. AI answers use your configured provider.

## Codex desktop handoff and background use

Version 0.5.0 adds an optional **Codex desktop conversation** destination. Sign in to Codex itself, copy a dedicated local conversation's `codex://threads/...` link, and paste it into **Destination / API / speech settings**. Select Codex, use **Check Codex conversation**, and save. No API key is needed for this mode. Prepare speech and calibrate normally, then choose **Minimize to tray**.

Look at anything on the calibrated primary monitor, hold **Ctrl+Alt+V**, speak, and release. One capture at press produces the **whole primary-screen overview** and a native-resolution gaze detail crop (up to 560×360 logical pixels). A thin rectangle links the detail image and a small cross marks approximate gaze. Both images come from the same frame, and the target stays frozen throughout speech. Codex mode uses a median of recent real gaze predictions without a minimum stability/spread threshold; webcam jitter does not block a question, but missing or expired predictions still do. No application/window lookup or overlap checks run. The app hides its own windows and gaze marker before capture; other visible apps and the desktop are included. Stale gaze and inconsistent display geometry/DPI are still rejected.

The app submits two in-memory PNG image inputs and the locally recognized question through Codex's local queue. Fixed image/gaze instructions are in English; the user's question is preserved in its original language, and the instructions ask Codex to answer in that language. The desktop app owns generation, its model/account settings, its queue and its conversation history. A busy conversation receives the question after its existing work. Composer drafts are not touched. Look to Ask does not switch to the receiving chat, scrape answers, simulate paste, use the clipboard, write screenshot files, or create notifications. Use Codex's own reminders and open its chat to read the answer. Native notification behavior depends on Codex/Windows settings and must be checked on your device.

The tray icon opens the control panel and offers recalibration, Stop camera and Quit. Its tooltip retains status/errors without popups. The gaze marker is hidden in background mode and is off by default in Codex mode; Advanced has a debug option. If Windows has no system tray, minimization retains a taskbar entry. Preferences persist; personal calibration remains memory-only and is repeated after full exit.

**Compatibility:** the adapter was exercised with Windows desktop package **26.1021.2667.0** and its bundled Codex **0.164.0-alpha.11.1**. It uses the version-dependent `thread/queue/add` protocol and the desktop wake link. The ordinary `codex queue` command only accepts text, and older npm CLIs may lack the required protocol. Auto-detection prefers the installed desktop component under `%LOCALAPPDATA%/OpenAI/Codex/bin`; an optional executable path is available. Updates may break this adapter; failed/uncertain delivery is reported without automatic retries or a hidden API fallback. A queued message cannot be recalled by cancelling Look to Ask. General ChatGPT desktop/web handoff is not implemented.

See [Codex handoff acceptance](docs/CODEX-HANDOFF.zh.md) for manual checks, limitations and the explicitly opt-in live fixture test.

## Complete a first API question

1. Launch the app. Camera and microphone do not start automatically.
2. Select your webcam; **Refresh cameras** refreshes names without recording frames.
3. Open **Destination / API / speech settings**, select the API destination, enter an image-capable model, API base URL and key, then save. Example base: `https://api.openai.com/v1`; the app appends `/chat/completions`.
4. Click **Start calibration** and follow the nine targets. Keep your head reasonably still. Recalibrate each session and after moving or changing the camera.
5. Text: look at a target, press **Ctrl+Alt+A**, inspect the crop, type your question and click Send.
6. Voice: choose a **Recognition language** matching your speech (Chinese is the default), select `medium`, save, click **Prepare speech model** and wait for Ready. Look steadily for about half a second, hold **Ctrl+Alt+V**, speak after the recording prompt, then release to send automatically.
7. Check the actual transcript, crop and answer. Close the answer window to clear context, or wait for completion and ask again.

**Recalibrate** repeats calibration, **Stop camera** releases the camera, and **Quit** exits. Advanced options contain nine/25-point calibration, capture resolution, independent accuracy measurement and a hotkey self-check. The app verifies actual 720p/1080p frames; higher resolution does not guarantee better gaze accuracy.

## Choose an interface language

Use **Language / 语言** at the top of the main window: **System / 跟随系统**, **简体中文**, or **English**. The choice saves immediately and applies the next time you launch the app; quit and reopen when convenient. It does not interrupt an active recording or question. New installations follow the system locale: Chinese uses Simplified Chinese, all other locales use English. Existing settings without a language choice retain Chinese.

The interface language is separate from **Recognition language** in API / speech settings. Switching the UI to English leaves Mandarin recognition unchanged. Questions, transcripts and AI answers retain their original text; the AI is instructed to answer in the question's language. API keys kept only in memory need to be re-entered after any restart. Installer language selection is independent from the app preference.

Translations use Qt's built-in translation system, with no extra runtime dependency. Contributors can edit the public English catalog and run the validation/compilation commands in [TRANSLATIONS.md](docs/TRANSLATIONS.md).

## Shortcuts and troubleshooting

| Shortcut | Action |
|---|---|
| Ctrl+Alt+V | Hold to speak; releasing V, Ctrl or Alt ends recording |
| Ctrl+Alt+Space | Additional voice shortcut; may conflict with other software |
| Ctrl+Alt+A | Freeze context for a typed question |
| Ctrl+Alt+R | Recalibrate |
| Ctrl+Alt+Q | Quit |

Close old instances before starting a new version. If a shortcut fails, inspect its registration status and run **Test voice shortcut** under Advanced options. This self-check does not record, capture or send. The mouse hold button is also available. Rejected triggers explain whether calibration, gaze, model preparation or another request is blocking them.

Speech uses faster-whisper with beam size 5 and reuses the loaded model. It prefers NVIDIA GPU/FP16 when optional runtimes are available, otherwise CPU/int8. Recoverable GPU load/inference errors fall back to CPU; status and diagnostics show the actual device. NVIDIA runtimes are proprietary, separately installed, and excluded from the ordinary bundle. See [speech settings, GPU setup and latency](docs/SPEECH.zh.md).

For Mandarin errors, select Chinese and inspect the original transcript. The microphone follows the Windows default input device. Low input or frequent full-scale samples produce a hint; the app does not replace words to hide errors. Close competing camera apps and check Windows device privacy permissions if capture fails.

Local APIs may use `http://127.0.0.1:PORT/v1`; remote endpoints require HTTPS. The provider must accept images. Requests have a 30-second timeout and cancellation, without automatic retries or redirects. Keys and provider response bodies are not echoed in errors.

## Demo and acceptance

Open `_internal/demo/targets.html` beside the installed executable, or `tests/manual/targets.html` in a source checkout, on the primary monitor. Use browser full-screen mode. Ask for the name/code at upper-left, center and lower-right, and check that each preview and answer refer to the selected region.

For target locking, start speaking while looking upper-left, move your eyes elsewhere during recording, then release. The question must still use the region frozen at press. Repeat three turns and test cancellation. These are real demo instructions; no recorded demonstration is claimed.

Chinese product scope and acceptance: [PRODUCT.zh.md](docs/PRODUCT.zh.md), [TESTING.md](docs/TESTING.md).

## Roadmap

These are planned areas of exploration, not features available in the current MVP. No delivery dates are committed.

- **More complete screenshot context.** Explore better crop selection and optional follow-up captures when the initial gaze region lacks relevant information. Keep the gaze-selected object as the anchor, with user control over additional context and what is shared.
- **Other AI chat destinations.** Build on the Codex desktop adapter to explore additional user-selected chats, including ChatGPT. Each destination needs its own attachment, conversation-targeting and background-delivery validation; none is assumed compatible.

## Architecture

```text
Webcam -> local EyeTrax / MediaPipe -> calibrated gaze
                                      |
Explicit trigger -> freeze real gaze -> hide own windows -> one capture
                                      |
                 gaze-region crop + close-up + crop coordinates
                                      |
Typed question OR hold-to-record -> local faster-whisper transcription
                                      |
             configurable multimodal API -> floating answer
```

| Modules | Responsibility |
|---|---|
| `gaze`, `worker` | Webcam, EyeTrax coordinate calibration, tracking thread |
| `calibration`, `validation` | Calibration targets and independent accuracy measurement |
| `context`, `screen_context` | Fresh/stable gaze, DPI conversion, API local crops and primary-screen overview and gaze detail |
| `codex_handoff`, `tray` | Two-image Codex queue transactions and an explicit background lifecycle without notifications |
| `speech`, `cuda_runtime`, `voice` | On-demand microphone, GPU/CPU recognition, target locking |
| `vision`, `ask` | Multimodal HTTP, preview, cancellation, floating answers, memory diagnostics |
| `settings`, `credentials`, `devices`, `desktop` | Preferences, optional Windows vault, camera names, lifecycle |
| `ui`, `platform_windows` | Controls, gaze marker, global shortcuts and key-release detection |
| `i18n`, `translations` | Qt interface translations; separate from recognition language and user content |

There is no database, microservice, agent framework, MCP, continuous listening or wake word. Codex desktop handoff is optional; other AI-chat destinations remain deferred.

## Privacy and limitations

Camera frames, eye features, personal calibration, audio, screenshots, questions and answers are not recorded to disk by this app. Calibration is in memory and must be repeated after restart. The microphone opens only while holding to talk and closes on release, cancellation, timeout, error or exit; recording is limited to 30 seconds.

Capture only follows your explicit trigger. API mode crops the primary-screen frame locally and sends only the gaze-region crop, close-up and question. Codex mode sends the **whole primary-screen overview**, gaze detail and question; all visible apps and desktop content on that display may be shared. It does not identify application windows, reject overlap, or capture other monitors. Codex persists its queue and conversation attachments/history under its own account policy, even though Look to Ask keeps images in memory. Text mode requires Send; voice mode automatically submits after release. Screenshot memory is cleared on successful handoff or cancellation; no continuous capture occurs.

Non-sensitive preferences use `%LOCALAPPDATA%\LookToAsk\settings.json`. The API key stays in memory unless you explicitly choose Remember, which uses Windows Credential Manager. Diagnostics keep the last 100 events in memory and exclude images, audio, questions, answers and keys. The system clipboard is not used for automatic handoff.

Only the primary monitor is supported. Webcam tracking is approximate and sensitive to head position and lighting. AI answers and speech recognition can be wrong. Native model loading/inference cannot be forcibly interrupted; cancelled results are discarded. Display geometry changes require restart/recalibration. Protected desktops and some accelerated windows may not capture correctly. Native dependencies make the package substantially larger than the source; model downloads are separate.

## Develop and build

Use Windows x64 and Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m look_to_ask
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
```

API environment defaults are `LOOK_TO_ASK_API_BASE_URL`, `LOOK_TO_ASK_API_MODEL`, `LOOK_TO_ASK_API_KEY`, with `OPENAI_*` fallbacks. Do not put keys in tracked scripts or command arguments.

[PACKAGING.md](docs/PACKAGING.md) explains PyInstaller onedir, NSIS, license resources and artifact checks. Building does not push, publish or create a Release.

## License

Original code and vendored EyeTrax: MIT. Dependencies and models retain their own licenses. Qt/PySide and FFmpeg have LGPL and native-library distribution obligations; MIT does not replace them. The installer uses official PyAV bindings with separately built minimal LGPL FFmpeg libraries; Microsoft CRT/UCRT DLLs are not bundled. Corresponding library sources, replacement instructions, optional NVIDIA runtime terms and native notices are documented in [DEPENDENCIES.md](docs/DEPENDENCIES.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The source repository excludes installers, dependency binaries and model weights. The local binary audit and test results are recorded in [LICENSE-AUDIT.zh.md](docs/LICENSE-AUDIT.zh.md). Binary copies must retain their notices, component-specific Intel terms and both source ZIPs.

The main window’s **Licenses · Qt / PySide6 LGPLv3** button opens public third-party notices and library replacement instructions without taking a screenshot. Binary deliveries must include both source ZIPs; see [RELINKING.md](docs/RELINKING.md). Older 0.4.5 test binaries are superseded and must not be distributed.
