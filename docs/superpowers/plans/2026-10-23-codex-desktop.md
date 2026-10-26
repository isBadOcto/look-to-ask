> Superseded on 2026-10-25: the user requested direct primary-screen overview + same-frame gaze detail, without application/window detection. Current behavior: docs/CODEX-HANDOFF.zh.md.

# Codex Desktop Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver gaze-bound window/detail screenshots and local speech questions to a chosen Codex desktop chat while Look to Ask remains in the tray.

**Architecture:** Keep current gaze, speech and API modules. Add isolated window-context, desktop-destination and tray units; route the existing question transaction by selected destination and preserve prior visibility state.

**Tech Stack:** Python 3.12, existing PySide6/Qt and Win32 APIs. No new runtime dependencies unless desktop feasibility requires a reviewed small binding.

**Spec:** `docs/superpowers/specs/2026-10-23-codex-desktop-design.md`

## Global Constraints

- No push/release; sole EyeTrax; local audio and active one-shot captures only.
- No custom notifications, answer scraping, new gaze engines or MCP.
- Retain API mode, bilingual UI and existing license/build policies.
- Do not claim Codex desktop delivery from a separate invisible CLI session.

## Review Focus

- Actual receiver identity, drafts/busy state and ambiguous submission.
- Hidden/minimized window restoration, cancelled generations and exit races.
- DPI/window boundaries, other-window occlusion and same-frame crop correspondence.
- Destination privacy and cleanup of any necessary temporary attachments.
- Repeated sends, no API requirement in desktop mode, native notification limits.

## Tasks

### 1. Window context
- [x] Add failing geometry/annotation/invalid-source tests in `tests/test_window_context.py`.
- [x] Implement `build_window_context(image, screen, gaze_global, window_rect)` and
  `capture_window_context(screen, gaze_global)` in `window_context.py`, using
  `ContextSnapshot` and `ContextGeometry` without changing API crop semantics.
- [x] Verify DPI, edges, source validation and real captured test-window geometry.

### 2. Codex destination
- [x] Prove desktop transport capabilities using non-private fixtures/metadata.
- [x] Add failing tests for destination settings, two-image payload, receiver
  binding, native draft preservation/busy queueing, cancellation and unknown send outcome.
- [x] Implement `codex_handoff.py` with asynchronous submission and explicit
  accepted/failed/unknown states; no private cloud endpoints or shared secrets.
- [x] Bind and validate the actual user-selected receiving conversation.

### 3. Background lifecycle
- [x] Add failing tray/visibility/marker tests, then implement `tray.py`.
- [x] Wire minimized state and explicit open/recalibrate/quit into `ui.py`.
- [x] Preserve window state in `ask.py`; route voice through selected destination
  in `voice.py`, with no preview in background and no API validation in Codex mode.
- [x] Verify shutdown, cancellation and repeated questions across both modes.

### 4. Product verification
- [x] Update saved settings, disclosures, English README, Chinese acceptance docs,
  AGENTS scope and all new TS/QM translations. Record any dependency changes.
- [x] Run pytest/ruff/pip check and targeted live desktop handoffs. Inspect the
  actual received attachments rather than relying on submission attempts.
- [ ] Report remaining physical camera/microphone/Windows version checks and
  directly executable manual steps. Stop without pushing.

## Completion evidence

2026-10-24: Real installed Codex accepted three paired-image fixture questions and answered the LEFT A7 / CENTER C8 / RIGHT B9 targets correctly. Foreground was unchanged. Native capture test passes at 1920×1080 / 100%; automated geometry tests cover scaled coordinates. Fresh review regressions now cover pre-hide source binding, lazy credential restoration and synchronous process errors. No new runtime dependencies. Local 0.5.0 packaging is the remaining delivery step; no more agent runs or live model sends are planned.
