# Read-only Windows hardware, driver, disk, startup, and event log diagnostics.
$ErrorActionPreference = 'SilentlyContinue'

Write-Output "=== PROBLEM DEVICES ==="
$badDevices = Get-PnpDevice | Where-Object { $_.Status -ne 'OK' -and $_.Present -eq $true } |
  Select-Object Class, FriendlyName, Status, InstanceId
if ($badDevices) { $badDevices | Format-Table -AutoSize | Out-String } else { Write-Output "None found." }

Write-Output "=== PHYSICAL DISKS ==="
Get-PhysicalDisk | Select-Object FriendlyName, MediaType, HealthStatus, OperationalStatus, @{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}} |
  Format-Table -AutoSize | Out-String

Write-Output "=== RECENT SYSTEM ERRORS (LAST 24H, TOP 15) ==="
$since = (Get-Date).AddHours(-24)
$sysEvents = Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=$since} -MaxEvents 15
if ($sysEvents) {
  $sysEvents | Select-Object TimeCreated, Id, ProviderName, @{N='Message';E={($_.Message -split "`r?`n")[0]}} |
    Format-Table -Wrap | Out-String
} else {
  Write-Output "No Critical/Error System events in the last 24 hours."
}

Write-Output "=== STARTUP ITEMS ==="
Get-CimInstance Win32_StartupCommand | Select-Object Name, Location, Command |
  Format-Table -Wrap | Out-String
