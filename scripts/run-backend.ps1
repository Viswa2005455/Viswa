# Runs the app's backend in the "Finance Studio - BACKEND" window and keeps it running.
#  * Turns off QuickEdit for this window: otherwise one click inside it selects text and Windows
#    pauses the backend until a key is pressed, so the website shows "API offline".
#  * Restarts the backend a few seconds after it stops. If it stops straight away three times in
#    a row (for example a startup error), it waits so the error stays on screen for a screenshot.
$sig = @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int nStdHandle);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
'@
try {
  $k = Add-Type -MemberDefinition $sig -Name Console -Namespace FisBackend -PassThru
  $h = $k::GetStdHandle(-10)  # standard input
  $mode = [uint32]0
  if ($k::GetConsoleMode($h, [ref]$mode)) {
    # clear ENABLE_QUICK_EDIT_MODE (0x40); ENABLE_EXTENDED_FLAGS (0x80) is needed for the change to apply
    [void]$k::SetConsoleMode($h, [uint32](($mode -band 0xFFFFFFBF) -bor 0x80))
  }
} catch {}

Set-Location (Join-Path $PSScriptRoot '..\backend')
$quickFails = 0
while ($true) {
  $started = Get-Date
  uv run uvicorn app.main:app --port 8000
  $code = $LASTEXITCODE
  if (((Get-Date) - $started).TotalSeconds -lt 20) { $quickFails++ } else { $quickFails = 0 }
  Write-Host ""
  if ($quickFails -ge 3) {
    Write-Host "The backend could not start (exit code $code). Send a screenshot of this window." -ForegroundColor Red
    Read-Host "Press Enter to try again, or close this window to stop the app"
    $quickFails = 0
  } else {
    Write-Host "The backend stopped (exit code $code). Restarting in 5 seconds - close this window to stop the app." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
  }
}
