# PC Control Safety & Execution Rules

When the `pc-control` plugin is active, follow these tiered guardrails across all MCP tools and PowerShell commands:

## 1. Action Tiers

- **Tier 1 — Read-Only (Run Freely)**:
  - `take_screenshot`, `list_windows`, `system_overview`, `list_processes`, `list_services`, `find_files`, `clipboard(action="get")`, and read-only PowerShell diagnostics (`Get-*`, `powercfg /list`, `netsh ... show`).
- **Tier 2 — Reversible UI & System Actions (Real-Time + Lock Guard)**:
  - Prefer `run_gui_sequence` over multiple single-step `mouse_action` / `keyboard_action` turns so the border ring + input lock stay active smoothly and complete in one round-trip.
  - Always release the control lock (`release_after=True` or `control_session(action="stop")`) as soon as the GUI task finishes.
  - If `ABORTED_BY_USER` is returned (`Ctrl+C`), halt GUI actions immediately.
  - Only interact with the application or setting the user asked about. If an unexpected dialog, login prompt, or permission screen appears, release control and ask the user.
- **Tier 3 — Destructive or High-Impact (Confirm First)**:
  - `stop_process`, `manage_window(action="close")` on unsaved work, deleting/moving files, uninstalling apps, stopping/disabling Windows services, firewall/network resets, and **all Windows Registry edits**.
  - **Before executing Tier 3 actions**: state the exact command or target, back up any registry key first (`reg export <key> <backup.reg> /y`), and get explicit user confirmation.

## 2. Strict Boundaries

- **Credentials & Sensitive Screens**: Never type into, screenshot-scrape, or auto-submit password managers, banking/payment flows, or 2FA prompts unless the user explicitly directs each step.
- **UAC / Elevation**: Windows User Account Control (UAC) prompts cannot be automated. If an action requires Administrator privileges and fails with Access Denied, inform the user clearly so they can run it elevated or confirm in an admin terminal.
- **CLI Before GUI**: Prefer PowerShell / `winget` / Win32 API tools over blind mouse clicking when both can accomplish the task reliably.
