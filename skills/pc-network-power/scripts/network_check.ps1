# Read-only Windows network adapter, Wi-Fi, and connectivity diagnostics.
$ErrorActionPreference = 'SilentlyContinue'

Write-Output "=== NETWORK ADAPTERS ==="
Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, LinkSpeed | Format-Table -AutoSize | Out-String

Write-Output "=== IP & DNS CONFIGURATION ==="
Get-NetIPConfiguration | Select-Object InterfaceAlias, IPv4Address, IPv4DefaultGateway, DNSServer | Format-List | Out-String

Write-Output "=== WI-FI INTERFACES ==="
netsh wlan show interfaces

Write-Output "=== DNS TEST (google.com) ==="
Resolve-DnsName -Name "google.com" -Type A | Select-Object Name, IPAddress, QueryType | Format-Table -AutoSize | Out-String
