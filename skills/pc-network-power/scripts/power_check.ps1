# Read-only Windows power plans, sleep states, and wake diagnostics.
$ErrorActionPreference = 'SilentlyContinue'

Write-Output "=== POWER PLANS ==="
powercfg /list

Write-Output "`n=== AVAILABLE SLEEP STATES ==="
powercfg /availablesleepstates

Write-Output "`n=== LAST WAKE SOURCE ==="
powercfg /lastwake

Write-Output "`n=== WAKE TIMERS ==="
powercfg /waketimers
