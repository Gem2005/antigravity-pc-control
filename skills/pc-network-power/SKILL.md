---
name: pc-network-power
description: >-
  Troubleshoot Windows networking (Wi-Fi, DNS, IP, adapters) and manage Windows
  power, sleep, hibernation, and battery settings. Use when the user asks to fix
  Wi-Fi/internet issues, flush DNS, check battery health, or tune sleep/power plans.
---

# Windows Network & Power Management

## Network Troubleshooting

1. **Inspect current state** using [network_check.ps1](./scripts/network_check.ps1):
   - Active network adapters, IP/gateway/DNS servers, Wi-Fi interface signal/SSID, and connectivity tests (gateway + DNS).
2. **Apply reversible fixes** (announce first):
   - Flush DNS cache: `ipconfig /flushdns`
   - Renew DHCP lease: `ipconfig /release` then `ipconfig /renew`
   - Restart a misbehaving adapter (ask confirmation first, as it drops connectivity briefly): `Restart-NetAdapter -Name "<AdapterName>"`

## Power & Battery Management

1. **Inspect power state** using [power_check.ps1](./scripts/power_check.ps1):
   - Lists active and available power plans (`powercfg /list`), supported sleep states (`powercfg /availablesleepstates`), and last wake source (`powercfg /lastwake`).
2. **Generate a battery health report** (laptops):
   - `powercfg /batteryreport /output "$env:TEMP\battery-report.html"`
3. **Tune settings** (confirm changes with user):
   - Switch active scheme: `powercfg /setactive <GUID>`
   - Adjust screen/sleep timeouts on AC or DC via `powercfg /change monitor-timeout-ac <mins>` or `standby-timeout-dc <mins>`.
