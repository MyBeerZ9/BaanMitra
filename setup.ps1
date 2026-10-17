# BaanMitra one-command setup. Every package installed below is free/open-source.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".\.venv")) {
    Write-Host "→ creating virtualenv (.venv)" -ForegroundColor Cyan
    python -m venv .venv
}

$py = ".\.venv\Scripts\python.exe"
Write-Host "→ upgrading pip" -ForegroundColor Cyan
& $py -m pip install --upgrade pip

Write-Host "→ installing free dependencies (requirements.txt)" -ForegroundColor Cyan
& $py -m pip install -r requirements.txt

Write-Host "→ installing BaanMitra itself (editable, so 'python -m baanmitra.*' works)" -ForegroundColor Cyan
& $py -m pip install -e .

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "→ created .env — open it and paste your FREE API keys" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "SETUP COMPLETE — total cost: Rs 0" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. .\.venv\Scripts\python.exe doctor.py   # requirements proof + missing-key checklist"
Write-Host "  2. notepad .env            # paste Groq / Supabase / Upstash / Twilio keys"
Write-Host "  3. .\.venv\Scripts\python.exe -m baanmitra.db --init      # print + apply the DDL"
Write-Host "  4. .\.venv\Scripts\python.exe -m baanmitra.seed           # seed circles + households"
Write-Host "  5. .\.venv\Scripts\python.exe -m baanmitra.api.main       # start API + dashboard"
Write-Host "  6. start http://localhost:8000/dashboard/"
