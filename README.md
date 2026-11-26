<div align="center">
  <img src="assets/logo.svg" alt="PC Control Logo" width="84" height="84" />
  <h1>PC Control — Antigravity Windows Plugin</h1>
  <p>
    <strong>Real-time desktop vision, batched GUI automation, animated control-lock overlay, and Windows system diagnostics packaged as a toggleable Antigravity plugin.</strong>
  </p>
  <p>
    <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?style=flat-square&logo=windows" alt="Platform: Windows" />
    <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
    <img src="https://img.shields.io/badge/MCP-FastMCP%20%2F%202.x-10B981?style=flat-square" alt="MCP" />
    <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License: MIT" />
  </p>
</div>

---

## Features

- **Real-Time Batched GUI Automation (`run_gui_sequence`)**: Chains `focus_window`, `click`, `paste_text`, `press`, `hotkey`, and `wait` in a **single MCP round-trip**, returning the updated screenshot in the same call.
- **Fast Screen-Share Buffer (`_ScreenWatcher`)**: Continuously buffers `1280px` JPEG frames in memory (`~0.35s` interval while active) for rapid desktop vision without heavy PNG compression lag.
- **Visual Control Ring & Physical Input Lock (`overlay_guard.py`)**:
  - Draws an animated multi-color glowing border ring around your primary monitor while Gemini controls your PC.
  - Uses Win32 low-level hooks (`WH_KEYBOARD_LL` / `WH_MOUSE_LL`) to block accidental human input while allowing injected automation events through.
  - Shows a floating top-center warning pill — **`Gemini has control of your PC • To stop, press Ctrl+C`** — whenever physical input is detected.
  - Pressing **`Ctrl+C`** immediately unlocks input, hides the ring/banner, and aborts the active sequence (plus a `25s` idle watchdog auto-release).
- **Window, App & Clipboard Control**: List visible Win32 windows, focus/minimize/maximize/restore/close windows, launch executables or files, and read/write the clipboard.
- **System Telemetry & Windows Playbooks**: Inspect CPU/RAM/disks/battery/processes/services, find files across user folders, and run curated PowerShell diagnostics for PnP devices, Event Viewer errors, Wi-Fi/DNS, `powercfg` battery/sleep tuning, `winget`, and backed-up registry edits.
- **Tiered Safety Rules (`rules/AGENTS.md`)**: Enforces read-only freedom, scoped reversible actions, explicit confirmation + registry backups for Tier-3 changes, and strict credential/UAC boundaries.

---

## Repository Structure

```text
pc-control/
├── assets/logo.svg                 # Plugin icon
├── docs/
│   ├── architecture.md             # System & Win32 overlay architecture
│   └── tools-reference.md          # Detailed reference for all 14 MCP tools
├── rules/AGENTS.md                 # Always-on safety & confirmation tiers
├── server/
│   ├── overlay_guard.py            # Win32 layered border ring + LL hooks
│   ├── pc_control_mcp.py           # MCP stdio server (14 tools)
│   ├── pyproject.toml              # Python dependencies (uv)
│   ├── uv.lock                     # Locked dependency graph
│   └── tests/test_pc_control.py    # Unit & MCP stdio integration tests
├── skills/
│   ├── pc-desktop-gui/SKILL.md     # Batched GUI & screen-share playbook
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
2. Pre-sync the Python environment (so MCP startup is instant):
   ```powershell
   uv --directory "$env:USERPROFILE\.gemini\config\plugins\pc-control\server" sync
   ```
3. Open **Skills & Customizations** in Antigravity and verify **PC Control** is enabled (toggle off/on after pulling updates to reload the MCP server).

---

## MCP Tools Overview (14 Tools)

| Category | Tools |
| :--- | :--- |
| **Control Guard** | `control_session` |
| **Vision & GUI** | `take_screenshot`, `run_gui_sequence`, `mouse_action`, `keyboard_action` |
| **Windows & Apps** | `list_windows`, `manage_window`, `launch_app`, `clipboard` |
| **System & Files** | `system_overview`, `list_processes`, `stop_process`, `list_services`, `find_files` |

See [docs/tools-reference.md](./docs/tools-reference.md) for full parameter schemas and examples.

---

## Documentation

- [Architecture Guide](./docs/architecture.md) — DPI awareness, `_ScreenWatcher` cache, `overlay_guard.py` Win32 hooks, and safety boundaries.
- [MCP Tools Reference](./docs/tools-reference.md) — Parameters, coordinate spaces, and sequence step schemas.
- [Changelog](./CHANGELOG.md) — Release history.
- [Contributing](./CONTRIBUTING.md) — Development setup and test suite instructions.

---

## Security & Platform Notes

- **Turn-based Vision**: Antigravity's agent loop is turn-based rather than a continuous WebRTC video stream; `_ScreenWatcher` keeps frames buffered in memory so tool calls return near-instantly.
- **Windows UIPI / UAC**: Elevation dialogs and Administrator-level windows run on Windows' protected desktop and cannot be automated or locked by standard-user hooks.
- **Safety Guardrails**: See [rules/AGENTS.md](./rules/AGENTS.md) for Tier 1–3 operational boundaries.
