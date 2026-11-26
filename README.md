<div align="center">
  <img src="assets/logo.svg" alt="PC Control Logo" width="84" height="84" />
  <h1>PC Control — Antigravity Windows Plugin</h1>
  <p>
    <strong>Windows UI Automation (zero-screenshot element control), a fast <code>pc-operator</code> Flash subagent, an optional local Gemini real-time worker, animated border-ring input lock, and system diagnostics packaged as a toggleable Antigravity plugin.</strong>
  </p>
  <p>
    <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?style=flat-square&logo=windows" alt="Platform: Windows" />
    <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
    <img src="https://img.shields.io/badge/MCP-17%20Tools-10B981?style=flat-square" alt="MCP: 17 Tools" />
    <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License: MIT" />
  </p>
</div>

---

## Features

- **Windows UI Automation (`get_ui_tree`, `ui_action`) — Zero-Screenshot Control**:
  - Reads live native Windows Accessibility controls (buttons, text boxes, tabs, menus, list items) in ~30–60ms and clicks or types into them by name/ID without encoding or uploading screenshots.
- **Multi-Agent Speedup (`agents/pc-operator.md`)**:
  - Ships a dedicated `pc-operator` subagent designed to run on `Model="flash"`, keeping your main conversation clean while executing multi-step Windows workflows much faster.
- **Local Real-Time Micro-Agent (`realtime_task`) — Optional `GEMINI_API_KEY` Mode**:
  - When `GEMINI_API_KEY` is set in `~/.env` (or environment variables), runs a tight local **Screen + UI Tree → Gemini Flash → Action** loop directly inside the MCP server with zero Antigravity turn overhead.
- **Batched GUI Sequences (`run_gui_sequence`) & Fast Screen Cache (`_ScreenWatcher`)**:
  - Chains `focus_window`, `click`, `paste_text`, `press`, `hotkey`, and `wait` in one MCP round-trip and returns a fast `1280px` JPEG frame.
- **Visual Control Ring & Physical Input Lock (`overlay_guard.py`)**:
  - Draws an animated multi-color glowing border ring around your primary monitor while Gemini controls your PC.
  - Uses Win32 low-level hooks (`WH_KEYBOARD_LL` / `WH_MOUSE_LL`) to block accidental human input while passing injected automation events through.
  - Pops up **`Gemini has control of your PC • To stop, press Ctrl+C`** on physical interrupts and unlocks immediately on **`Ctrl+C`** (plus a `25s` idle watchdog).
- **System Telemetry & Windows Playbooks**: Inspect CPU/RAM/disks/battery/processes/services, find files across user folders, and run curated PowerShell diagnostics for devices, drivers, Wi-Fi/DNS, `powercfg`, `winget`, and backed-up registry edits.

---

## Repository Structure

```text
pc-control/
├── agents/pc-operator.md           # Fast subagent for multi-step UI execution
├── assets/logo.svg                 # Plugin icon
├── docs/
│   ├── architecture.md             # UIA, real-time loop, and Win32 overlay architecture
│   └── tools-reference.md          # Detailed reference for all 17 MCP tools
├── rules/AGENTS.md                 # Always-on safety & confirmation tiers
├── server/
│   ├── overlay_guard.py            # Win32 layered border ring + LL hooks
│   ├── pc_control_mcp.py           # MCP stdio server (17 tools)
│   ├── realtime_worker.py          # Local Gemini Flash Vision+UIA worker
│   ├── ui_tree.py                  # Windows UI Automation (UIA) helpers
│   ├── pyproject.toml              # Python dependencies (uv)
│   ├── uv.lock                     # Locked dependency graph
│   └── tests/test_pc_control.py    # Unit & MCP stdio integration tests
├── skills/
│   ├── pc-desktop-gui/SKILL.md     # UIA + Flash subagent + real-time playbook
│   ├── pc-diagnostics/             # Hardware, drivers, disks & Event Log
│   ├── pc-network-power/           # Wi-Fi, DNS, adapters & powercfg
│   └── pc-maintenance/             # Services, winget, cleanup & registry
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── mcp_config.json                 # Portable uv stdio launcher
└── plugin.json                     # Antigravity plugin manifest
```

---

## Installation (Antigravity)

### Prerequisites
- **Windows 10 / 11**
- **[uv](https://docs.astral.sh/uv/)** (`>= 0.5`) and **Python 3.11+**

### Setup
1. Clone directly into your Antigravity global plugins directory:
   ```powershell
   git clone https://github.com/Gem2005/antigravity-pc-control.git "$env:USERPROFILE\.gemini\config\plugins\pc-control"
   ```
2. Sync the Python environment:
   ```powershell
   uv --directory "$env:USERPROFILE\.gemini\config\plugins\pc-control\server" sync
   ```
3. *(Optional)* Enable the local `realtime_task` micro-agent by adding your Gemini API key to `~\.env` (never paste keys into chat):
   ```powershell
   "GEMINI_API_KEY=your_api_key_here" | Out-File -FilePath "$env:USERPROFILE\.env" -Encoding utf8 -Append
   ```
4. Open **Skills & Customizations** in Antigravity and verify **PC Control** is enabled (toggle off/on after updating).

---

## MCP Tools Overview (17 Tools)

| Category | Tools |
| :--- | :--- |
| **Control Guard** | `control_session` |
| **UI Automation (No Screenshot)** | `get_ui_tree`, `ui_action` |
| **Local Real-Time Worker** | `realtime_task` |
| **Vision & Batched GUI** | `take_screenshot`, `run_gui_sequence`, `mouse_action`, `keyboard_action` |
| **Windows, Apps & Clipboard** | `list_windows`, `manage_window`, `launch_app`, `clipboard` |
| **System & Files** | `system_overview`, `list_processes`, `stop_process`, `list_services`, `find_files` |

See [docs/tools-reference.md](./docs/tools-reference.md) for full parameter schemas and examples.

---

## Documentation

- [Architecture Guide](./docs/architecture.md)
- [MCP Tools Reference](./docs/tools-reference.md)
- [Changelog](./CHANGELOG.md)
- [Contributing](./CONTRIBUTING.md)
