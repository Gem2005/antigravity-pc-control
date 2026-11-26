---
name: pc-desktop-gui
description: >-
  Operate native Windows desktop applications in real time using batched GUI
  sequences, fast screen-share screenshots, mouse actions, keyboard shortcuts,
  and window management via the pc-control MCP server. Use when the user asks to
  interact with a desktop app, click UI elements, type into windows, switch/arrange
  windows, or visually inspect the desktop screen.
---

# Windows Desktop GUI Control (Real-Time)

Use `run_gui_sequence` and `control_session` from `pc-control` to control Windows desktop apps fast with minimal round-trips.

## Fast Workflow

1. **Inspect Screen (`take_screenshot`)**:
   - Call `take_screenshot` (defaults to fast `1280px` JPEG with background screen-share cache).
   - Use `list_windows` only if the target app isn't visible yet.
2. **Batch Actions in One Call (`run_gui_sequence`)**:
   - Combine `focus_window`, `click`, `paste_text` / `type`, `press` / `hotkey`, and `wait` into a **single `run_gui_sequence` call** instead of separate turns for each click or keystroke.
   - Set `auto_lock=True` (default) so the animated border ring appears and physical user mouse/keyboard input is locked during control.
   - Set `release_after=True` on the final sequence of your task (or call `control_session(action="stop")`) so the border ring disappears and PC controls unlock immediately when done.
   - `run_gui_sequence` returns an updated screenshot automatically (`return_screenshot=True`) so you don't need an extra `take_screenshot` turn.
3. **Respect `Ctrl+C` User Interrupts**:
   - If a tool returns `ABORTED_BY_USER`, stop automating immediately, confirm control was returned to the user, and ask what they want to do next.

## Guardrails

- Confirm before closing windows that may contain unsaved work (`manage_window(action="close")`).
- Stop and ask the user if an unexpected popup, login prompt, or UAC dialog appears.
