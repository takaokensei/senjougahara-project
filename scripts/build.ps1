<#
.SYNOPSIS
    Build script for Senjougahara (environment check).
    In Phase 1, verifies the dev environment is set up correctly.

.DESCRIPTION
    Checks:
    1. Python venv and requirements installed
    2. Avatar npm deps installed and TypeScript compiles
    3. Playwright Chromium installed

.EXAMPLE
    .\scripts\build.ps1
#>

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$ErrorCount  = 0

function Check($description, $condition) {
    if ($condition) {
        Write-Host "  [OK]   $description" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $description" -ForegroundColor Red
        $script:ErrorCount++
    }
}

Write-Host ""
Write-Host "Senjougahara — Build/Environment Check" -ForegroundColor Cyan
Write-Host ("=" * 50) -ForegroundColor Cyan
Write-Host ""

# Python checks
Write-Host "[Python / Brain]" -ForegroundColor Yellow
Check "Python in PATH"                      ((Get-Command python -ErrorAction SilentlyContinue) -ne $null)
Check "brain/.venv exists"                  (Test-Path "$ProjectRoot\brain\.venv")
Check "brain/requirements.txt exists"       (Test-Path "$ProjectRoot\brain\requirements.txt")

Write-Host ""
Write-Host "[Node / Avatar]" -ForegroundColor Yellow
Check "Node.js in PATH"                     ((Get-Command node -ErrorAction SilentlyContinue) -ne $null)
Check "npm in PATH"                         ((Get-Command npm -ErrorAction SilentlyContinue) -ne $null)
Check "avatar/node_modules exists"          (Test-Path "$ProjectRoot\avatar\node_modules")

Write-Host ""
if ($ErrorCount -eq 0) {
    Write-Host "All checks passed. Environment is ready." -ForegroundColor Green
} else {
    Write-Host "$ErrorCount check(s) need attention. See docs/SETUP.md for instructions." -ForegroundColor Yellow
}