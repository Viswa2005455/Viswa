# Stops an earlier copy of Finance Intelligence Studio that is still running (for example the
# BACKEND and WEBSITE windows of an older download), so this copy can use ports 8000 and 5173.
# A program is stopped only if it answers like this app; other programs are never touched.
$ErrorActionPreference = 'SilentlyContinue'
$checks = @(
  @{ Port = 8000; Url = 'http://localhost:8000/api/health'; Match = 'database_engine'; Name = 'backend' },
  @{ Port = 5173; Url = 'http://localhost:5173/'; Match = 'Finance Intelligence Studio'; Name = 'website' }
)
$blocked = @()
foreach ($c in $checks) {
  $ids = @(Get-NetTCPConnection -LocalPort $c.Port -State Listen |
           Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })
  if ($ids.Count -eq 0) { continue }
  $ours = $false
  try { $ours = (Invoke-WebRequest -UseBasicParsing $c.Url -TimeoutSec 3).Content -match $c.Match } catch {}
  if ($ours) {
    Write-Host "       An earlier copy of the app's $($c.Name) is still running. Stopping it..."
    foreach ($id in $ids) { Stop-Process -Id $id -Force }
  } else {
    $blocked += $c.Port
  }
}
if ($blocked.Count -gt 0) {
  Write-Host ""
  Write-Host "Port(s) $($blocked -join ', ') are being used by another program on this computer."
  Write-Host "Close that program (or restart the computer), then double-click start-windows.bat again."
  exit 2
}
Start-Sleep -Seconds 1
exit 0
