$ErrorActionPreference = "Stop"

Write-Host "====================================="
Write-Host "Trade-Swing-Bot Validation"
Write-Host "====================================="
Write-Host ""

Write-Host "Step 1: Python compile check"
Get-ChildItem .\src\swing_trade_bot\*.py | ForEach-Object {
    python -m py_compile $_.FullName
}
Write-Host "Python compile: PASSED"
Write-Host ""

Write-Host "Step 2: Pytest suite"
python -m pytest -q
Write-Host ""
Write-Host "STATUS: VALIDATION COMPLETE"
