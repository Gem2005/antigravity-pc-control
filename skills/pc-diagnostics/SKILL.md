---
name: pc-diagnostics
description: >-
  Diagnose Windows PC hardware, devices, drivers, Event Viewer errors, disk/RAM/CPU
  usage, and startup programs. Use when the user asks to check device status,
  troubleshoot drivers, find why their PC is slow, or run a system health check.
---

# Windows PC Diagnostics

Combine the `pc-control` MCP telemetry tools with PowerShell diagnostics to pinpoint hardware, driver, resource, and stability issues.

## Steps

1. **Quick Resource Snapshot**:
   - Call the `system_overview` MCP tool for CPU, RAM, disks, battery, and top memory-consuming processes.
   - Call `list_processes` (`sort_by="cpu"` or `"memory"`) if deeper process inspection is needed.
2. **Run Read-Only Hardware & Event Check**:
   - Execute [diagnose.ps1](./scripts/diagnose.ps1) via PowerShell to inspect:
     - Problem PnP devices (`ConfigManagerErrorCode -ne 0`)
     - Recent Critical/Error events in the `System` and `Application` logs (last 24h)
     - Physical disk health (`Get-PhysicalDisk`)
     - Startup commands (`Win32_StartupCommand`)
3. **Report & Recommend**:
   - Summarize findings clearly (healthy vs. warnings/errors).
   - Propose specific remediation steps and ask for confirmation before stopping processes, updating/restarting drivers, or editing startup/registry entries.
