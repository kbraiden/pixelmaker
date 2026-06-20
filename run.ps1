# PixelMaker launcher (Windows / PowerShell)
# Creates a virtual environment, installs dependencies, starts the server,
# and opens your browser. Re-run any time to start the app.
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not on PATH. Install Python 3.10+ from https://www.python.org/downloads/ and try again."
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
    & $python -m venv .venv
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements.txt

$url = "http://${BindHost}:${Port}"
Write-Host "Starting PixelMaker at $url" -ForegroundColor Green
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 2; Start-Process $u } -ArgumentList $url | Out-Null

& $venvPy -m uvicorn app.main:app --host $BindHost --port $Port
