> Superseded on 2026-10-25: the user requested direct primary-screen overview + same-frame gaze detail, without application/window detection. Current behavior: docs/CODEX-HANDOFF.zh.md.

# Codex desktop handoff — approved scope

用户在 2026-10-23 已明确批准本方案并要求实现、测试、提供人工验收，不推送。

## Experience

- Preserve EyeTrax calibration, camera choices, text/API and local faster-whisper speech.
- Add an optional Codex desktop destination. User binds one receiving conversation;
  press freezes stable gaze and one source-window capture, release transcribes locally
  and automatically submits two images plus the question to that conversation.
- Image 1 is the gaze-selected window's currently visible area, including window
  chrome. Image 2 is a native-resolution local crop. Mark image 2's rectangle on
  image 1, with explicit gaze coordinates and approximate-target instructions.
- Both images come from one acquisition before changing focus. Do not capture
  continuously, scroll, substitute the cursor for gaze, or expand to other windows.
- Minimize to a tray icon; background voice capture/transcription/handoff never
  opens this app's preview/control window or gaze marker. Tray offers open,
  recalibrate, stop camera and quit. No notifications or answer-completion monitor.
- Settings persist; personal calibration remains memory-only and must be repeated
  after full exit. Camera local; microphone held only; audio never stored/uploaded.

## Approaches and decision

Fixed local crops lose chart/paragraph context. Semantic UI/OCR cropping adds
complexity and has incomplete coverage. User selected window overview plus local
detail, with no toolbar/address-bar filtering. A separate API/CLI-only invisible
conversation is not equivalent to delivery into the user's Codex desktop chat.

Prefer a supported local desktop transport. If unavailable, validate native UI
handoff against the actual desktop client; never claim delivery without evidence.
Do not use hidden cloud endpoints, copy tokens, ship Codex credentials, or use
this coding session's tools as a runtime dependency. No MCP/agent framework.

## Failure and privacy boundaries

Reject stale/unstable/outside-primary gaze, desktop/own-window targets, geometry
changes and invalid captures. Do not silently capture/upload the whole desktop.
Reject unknown/changed receiver. Use the native queue behind busy work and leave
composer drafts untouched. No automatic retry after an ambiguous submission.
Cancel/exit prevents pending submission;
an accepted external message cannot be recalled by closing this app.

Images/questions are temporary in memory where the transport permits. If native
attachment APIs require files, use an explicitly disclosed per-user temporary
folder, no OneDrive/repository path, guaranteed cleanup after ingestion/cancel and
startup recovery. Destination conversation history follows Codex's own policy.
Logs contain metadata only. Do not include chat contents, screenshots or keys.

## Acceptance

- Independent geometry tests at 100/125/150/200% and screen edges; same-frame
  overview/detail alignment, unmodified detail and visible correspondence box.
- Existing API behavior unchanged. Codex mode does not require API credentials.
- Three sequential handoffs deliver correct images/questions to one bound desktop
  chat, including minimized operation and gaze movement while speaking.
- Draft/busy/receiver loss/capture error/cancel/exit do not cause wrong or duplicate
  sends. Background work never restores hidden app windows. No notifications.
- pytest, ruff, pip check and translation compilation; clearly separate fixtures,
  live desktop checks, camera/microphone checks and unverified native notifications.

## Implementation rulings

- Work on local `codex/desktop-handoff` in the existing checkout to reuse the tested
  native environment; leave `main` intact and do not push or publish.
- Desktop transport compatibility is the first live experiment, not an assumed
  success. Any client limitation must remain explicit in the acceptance report.
