Param()
$ErrorActionPreference = 'Stop'

Write-Host "[Runner] Flushing DB and artifacts..."
python .\flush_all_files.py --all | Write-Output

Write-Host "[Runner] Starting 4-week English MobileChat simulation..."
$enOut = Join-Path (Get-Location) 'simulation_output\\mobile_4week'
New-Item -ItemType Directory -Force -Path $enOut | Out-Null
$env:MOBILE_SIM_WEEKS = '4'
& python .\mobile_chat_simulation.py *>&1 | Tee-Object -FilePath (Join-Path $enOut 'terminal_output.txt')

Write-Host "[Runner] English run finished. Flushing DB and artifacts..."
python .\flush_all_files.py --all | Write-Output

Write-Host "[Runner] Starting 4-week Korean MobileChat simulation..."
$koOut = Join-Path (Get-Location) 'simulation_output\\mobile_4week_ko'
New-Item -ItemType Directory -Force -Path $koOut | Out-Null
$env:MOBILE_SIM_WEEKS = '4'
& python .\mobile_chat_simulation_ko.py *>&1 | Tee-Object -FilePath (Join-Path $koOut 'terminal_output.txt')

Write-Host "[Runner] All runs completed."
