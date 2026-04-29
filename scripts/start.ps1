#!/usr/bin/env pwsh
# On-Call Copilot — Startup Script (PowerShell)
# Usage:
#   .\scripts\start.ps1                  # Start both agent server + UI
#   .\scripts\start.ps1 -SkipUI          # Start agent server only
#   .\scripts\start.ps1 -MockMode        # Start in mock mode (no Azure needed)
#   .\scripts\start.ps1 -SkipInstall     # Skip pip install step

param(
    [switch]$SkipUI,
    [switch]$MockMode,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $Root

# ─── preflight checks ────────────────────────────────────────────────────────

Write-Host "`n=== On-Call Copilot — Startup ===" -ForegroundColor Cyan

# Python
$python = $null
foreach ($cmd in "python3", "python") {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $python = $cmd; break }
}
if (-not $python) {
    Write-Host "ERROR: Python 3.10+ is required. Install from https://python.org" -ForegroundColor Red
    Pop-Location; exit 1
}
$pyVersion = & $python --version 2>&1
Write-Host "[check] $pyVersion" -ForegroundColor Green

# Azure CLI (skip check in mock mode)
if (-not $MockMode) {
    if (-not (Get-Command "az" -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: Azure CLI is required. Install from https://aka.ms/install-az-cli" -ForegroundColor Red
        Pop-Location; exit 1
    }
    Write-Host "[check] Azure CLI found" -ForegroundColor Green
}

# ─── virtual environment ─────────────────────────────────────────────────────

$venvDir = Join-Path $Root ".venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "`n[setup] Creating virtual environment..." -ForegroundColor Yellow
    & $python -m venv $venvDir
}

$activateScript = Join-Path $venvDir "Scripts" "Activate.ps1"
if (-not (Test-Path $activateScript)) {
    # Linux/macOS path
    $activateScript = Join-Path $venvDir "bin" "Activate.ps1"
}
. $activateScript
Write-Host "[check] Virtual environment activated" -ForegroundColor Green

# ─── dependencies ────────────────────────────────────────────────────────────

if (-not $SkipInstall) {
    Write-Host "`n[setup] Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt --quiet
    Write-Host "[check] Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "[skip]  Dependency install skipped" -ForegroundColor DarkGray
}

# ─── environment file ────────────────────────────────────────────────────────

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    $exampleFile = Join-Path $Root ".env.example"
    if (Test-Path $exampleFile) {
        Copy-Item $exampleFile $envFile
        Write-Host "[setup] Created .env from .env.example — edit it with your Azure values" -ForegroundColor Yellow
        Pop-Location; exit 1
    } else {
        Write-Host "WARNING: No .env file found. Set environment variables manually." -ForegroundColor Yellow
    }
}

# ─── azure login check (skip in mock mode) ───────────────────────────────────

if (-not $MockMode) {
    $account = az account show 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[auth] Not signed in to Azure. Running 'az login'..." -ForegroundColor Yellow
        $tenantId = $null
        if (Test-Path $envFile) {
            $tenantLine = Select-String -Path $envFile -Pattern "^AZURE_TENANT_ID=" -SimpleMatch
            if ($tenantLine) {
                $tenantId = ($tenantLine.Line -split "=", 2)[1].Trim('"', "'", " ")
            }
        }
        if ($tenantId) {
            az login --tenant $tenantId
        } else {
            az login
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Azure login failed." -ForegroundColor Red
            Pop-Location; exit 1
        }
    }
    Write-Host "[check] Azure CLI authenticated" -ForegroundColor Green
}

# ─── start servers ───────────────────────────────────────────────────────────

if ($MockMode) {
    Write-Host "`n[start] Launching mock server (no Azure needed)..." -ForegroundColor Cyan
    $env:MOCK_MODE = "true"
    & $python -m app.main
} else {
    if ($SkipUI) {
        Write-Host "`n[start] Launching agent server on http://localhost:8088 ..." -ForegroundColor Cyan
        & $python main.py
    } else {
        Write-Host "`n[start] Launching agent server on http://localhost:8088 ..." -ForegroundColor Cyan
        Write-Host "[start] Launching UI server on http://localhost:7860 ..." -ForegroundColor Cyan
        Write-Host "[info]  Press Ctrl+C to stop both servers.`n" -ForegroundColor DarkGray

        $agentJob = Start-Job -ScriptBlock {
            param($root, $python, $activate)
            Set-Location $root
            . $activate
            & $python main.py
        } -ArgumentList $Root, $python, $activateScript

        # Small delay so the agent server begins listening before the UI connects
        Start-Sleep -Seconds 3

        try {
            & $python ui/server.py
        } finally {
            Write-Host "`n[stop] Shutting down agent server..." -ForegroundColor Yellow
            Stop-Job $agentJob -ErrorAction SilentlyContinue
            Remove-Job $agentJob -Force -ErrorAction SilentlyContinue
        }
    }
}

Pop-Location
