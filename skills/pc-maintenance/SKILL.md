---
name: pc-maintenance
description: >-
  Inspect and manage Windows services, installed applications (winget), disk
  cleanup previews, and safe Windows Registry checks/backups. Use when the user
  asks to start/stop/restart a service, install/update apps, free disk space,
  or inspect/tweak registry settings.
---

# Windows System Maintenance

## Services

1. Call the `list_services` MCP tool first (`filter_text=...`, `status=...`) to find exact service names.
2. Before `Start-Service`, `Stop-Service`, or `Restart-Service`, confirm with the user if stopping or restarting a critical or unfamiliar service.

## Software Management (`winget`)

- Search: `winget search "<query>"`
- Check outdated packages: `winget upgrade`
- Install / upgrade (confirm package ID with user first): `winget install --id <Id> -e` or `winget upgrade --id <Id> -e`

## Disk Space & Temp Cleanup

1. Inspect space with `system_overview` or `find_files`.
2. Preview large temp/cache folders before deleting anything; **always ask explicit user confirmation** before removing files.

## Registry Tweaks (Strict Backup Rule)

1. Read first with `Get-ItemProperty -Path "HKCU:\..."` (or `reg query`).
2. **Before any write**, export a backup `.reg` file (`reg export "<key>" "$env:TEMP\reg-backup.reg" /y`) and confirm the exact key, value name, old value, and new value with the user.
