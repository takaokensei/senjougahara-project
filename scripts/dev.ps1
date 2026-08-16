<#
.SYNOPSIS
    Runs brain and avatar together in development mode.
    Starts both processes with clear labeled output.

.DESCRIPTION
    1. Checks for required prerequisites (.venv, node_modules)
    2. Starts brain (Python) in a background job
    3. Starts avatar (Electron) in a background job
    4. Ctrl+C kills both

.EXAMPLE
    .\scripts\dev.ps1
    .\scripts\dev.ps1 -BrainOnly
    .\scripts\dev.ps1 -AvatarOnly
#>

[CmdletBinding()]
param(
    [switch]$BrainOnly,
    [switch]$AvatarOnly
)

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$BrainVenv   = Join-Path $ProjectRoot "brain" ".venv" "Scripts" "python.exe"
$AvatarDir   = Join-Path $ProjectRoot "avatar"

# Check prerequisites
if (-not $AvatarOnly) {
    if (-not (Test-Path $BrainVenv)) {
        Write-Warning "Brain venv not found at $BrainVenv"
        Write-Warning "Run: python -m venv brain\.venv && brain\.venv\Scripts\pip install -r brain\requirements.txt"
        if ($BrainOnly) { exit 1 }
    }
}

if (-not $BrainOnly) {
    if (-not (Test-Path (Join-Path $AvatarDir "node_modules"))) {
        Write-Warning "Avatar node_modules not found. Run: npm --prefix avatar install"
        if ($AvatarOnly) { exit 1 }
    }
}

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "  Senjougahara Dev Mode" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

$brainJob   = $null
$avatarJob  = $null

if (-not $AvatarOnly) {
    Write-Host "[BRAIN] Starting Python brain..." -ForegroundColor Yellow
    $brainJob = Start-Job -ScriptBlock {
        param($root, $venv)
        Set-Location $root
        & $venv -m brain.main 2>&1 | ForEach-Object { "[BRAIN] $_" }
    } -ArgumentList $ProjectRoot, $BrainVenv
}

if (-not $BrainOnly) {
    Write-Host "[AVATAR] Starting Electron avatar..." -ForegroundColor Green
    $avatarJob = Start-Job -ScriptBlock {
        param($avatarDir)
        Set-Location $avatarDir
        npm run start:electron 2>&1 | ForEach-Object { "[AVATAR] $_" }
    } -ArgumentList $AvatarDir
}

Write-Host ""
Write-Host "Both processes started. Press Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "Chat endpoint: http://127.0.0.1:8767/chat" -ForegroundColor Cyan
Write-Host "Health endpoint: http://127.0.0.1:8766/health" -ForegroundColor Cyan
Write-Host ""

try {
    while ($true) {
        Start-Sleep -Seconds 1
        if ($brainJob)   { Receive-Job $brainJob   | Write-Host }
        if ($avatarJob)  { Receive-Job $avatarJob  | Write-Host }

        if ($brainJob -and $brainJob.State -eq 'Completed') {
            Write-Warning "[BRAIN] Process exited!"
            break
        }
        if ($avatarJob -and $avatarJob.State -eq 'Completed') {
            Write-Warning "[AVATAR] Process exited!"
            break
        }
    }
} finally {
    Write-Host "" ; Write-Host "Stopping all processes..." -ForegroundColor Yellow
    if ($brainJob)  { Stop-Job $brainJob;  Remove-Job $brainJob  }
    if ($avatarJob) { Stop-Job $avatarJob; Remove-Job $avatarJob }
    Write-Host "Done." -ForegroundColor Green
}