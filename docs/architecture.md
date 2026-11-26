# Architecture

`pc-control` combines four Antigravity plugin primitives with a 3-tier execution engine designed to minimize vision and turn-loop latency:

```text
Antigravity Agent (Main or pc-operator Flash Subagent)
  ├── agents/pc-operator.md        (Subagent definition for fast Model="flash" delegation)
  ├── rules/AGENTS.md              (Always-on Tier 1/2/3 safety guardrails)
  ├── skills/*/SKILL.md + *.ps1    (Playbooks for UIA, GUI, diagnostics, network/power, maintenance)
  └── mcp_config.json              (Spawns local stdio MCP server via uv)
        └── server/pc_control_mcp.py (17 tools)
              ├── ui_tree.py       (Windows UI Automation tree + element actions)
              ├── realtime_worker.py (Optional local Gemini Flash Vision+UIA loop)
              ├── _ScreenWatcher   (Background 1280px JPEG frame buffer)
              ├── Win32 / psutil   (Windows, processes, services, files)
              └── _GuardClient ──► server/overlay_guard.py
                                     ├── 4x UpdateLayeredWindow border strips
                                     ├── 1x Top-center interrupt warning pill
                                     └── WH_KEYBOARD_LL + WH_MOUSE_LL hooks
```

## 1. Three-Speed GUI Execution Strategy

1. **Zero-Screenshot UI Automation (`server/ui_tree.py`)**: Uses `uiautomation` inside `UIAutomationInitializerInThread()` to read native Windows controls (`Button`, `Edit`, `TabItem`, `MenuItem`, etc.) and click or set text directly by control name/ID in ~30–60ms.
2. **Multi-Agent Delegation (`agents/pc-operator.md`)**: Offloads multi-step desktop navigation to a dedicated `pc-operator` subagent pinned to `Model="flash"`, avoiding main-conversation context bloat.
3. **Local Real-Time Worker (`server/realtime_worker.py`)**: When `GEMINI_API_KEY` is configured in the environment or `~/.env`, `realtime_task` runs a tight local Vision+UIA loop using `google-genai` (`gemini-2.5-flash` by default) directly inside Python without Antigravity's per-turn context overhead.

## 2. DPI Awareness & Background Screen Buffer

Both `pc_control_mcp.py` and `overlay_guard.py` enable `SetProcessDpiAwareness(2)` (Per-Monitor DPI Aware) before initializing `mss`, `pyautogui`, or Win32 windows so screenshot pixels and cursor coordinates align 1:1. `_ScreenWatcher` buffers `1280px` JPEG frames every `~0.35s` when active and exits after `30s` of inactivity.

## 3. Overlay Ring & Physical Input Lock (`overlay_guard.py`)

`overlay_guard.py` runs in a separate Win32 message-pump process with click-through layered border windows (`WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`) and `WH_KEYBOARD_LL` / `WH_MOUSE_LL` hooks. Automation events (`LLKHF_INJECTED` / `LLMHF_INJECTED`) pass through, physical input triggers the top-center warning pill, and physical **`Ctrl+C`** (or the `25s`–`30s` watchdog) immediately unlocks the PC.
