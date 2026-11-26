---
name: pc-desktop-gui
description: >-
  Operate native Windows desktop applications fast using Windows UI Automation
  (zero-screenshot element control), the pc-operator flash subagent, local
  Gemini real-time worker (when GEMINI_API_KEY is set), batched GUI sequences,
  and fast screen-share screenshots. Use when the user asks to interact with a
  desktop app, click UI elements, type into windows, or inspect the desktop.
---

# Windows Desktop GUI Control (UIA + Multi-Agent + Real-Time)

Choose the fastest execution path for desktop GUI tasks:

1. **Local Real-Time Worker (`realtime_task`) — Fastest when `GEMINI_API_KEY` is set**:
   - Check `control_session(action="status")` -> `has_gemini_api_key`.
   - When `true`, delegate multi-step GUI goals directly to `realtime_task(goal=..., window_title=...)` so a tight local Gemini Flash Vision+UIA loop executes directly without Antigravity turn latency.
2. **UI Automation First (`get_ui_tree` + `ui_action`) — Zero Screenshots**:
   - For standard Windows apps (Settings, Explorer, Notepad, Teams, WhatsApp, Chrome controls), call `get_ui_tree` to list interactive elements (~30ms) and interact directly via `ui_action` (`click`, `set_text`, `focus`).
3. **Multi-Agent (`pc-operator` with `Model="flash"`)**:
   - For long or multi-step UI tasks without `GEMINI_API_KEY`, delegate execution to `invoke_subagent(TypeName="pc-operator", Model="flash", ...)` so the fast Flash model drives the UI loop while keeping the main conversation context clean.
4. **Batched Sequences (`run_gui_sequence`) for Canvas / Custom UIs**:
   - For drawing/canvas/custom graphics (e.g. Paint), take one fast JPEG `take_screenshot`, batch all clicks/drags/typing into a single `run_gui_sequence(auto_lock=True, release_after=True)`, and inspect the returned screenshot.

## Guardrails

- Always release the border-ring lock (`release_after=True` or `control_session(action="stop")`) when finished.
- On `ABORTED_BY_USER` (`Ctrl+C`), halt immediately and return control to the user.
- Never inspect or leak `GEMINI_API_KEY`; read it only from environment or `~/.env`.
