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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue
if (-not $ScriptDir -and $PSScriptRoot) {
    $ScriptDir = $PSScriptRoot
}
$ProjectRoot = if ($ScriptDir) { Split-Path $ScriptDir -Parent } else { (Get-Location).Path }
$BrainVenv   = "$ProjectRoot\brain\.venv\Scripts\python.exe"
$AvatarDir   = "$ProjectRoot\avatar"

# Check prerequisites
if (-not $AvatarOnly) {
    if (-not (Test-Path $BrainVenv)) {
        # Check if system python has dependencies installed
        $SysPython = Get-Command python -ErrorAction SilentlyContinue
        if ($SysPython) {
            Write-Host "[BRAIN] Using system python: $($SysPython.Source)" -ForegroundColor Cyan
            $BrainPython = "python"
        } else {
            Write-Warning "Brain venv not found at $BrainVenv and system python not found."
            Write-Warning "Run: uv venv brain\.venv && uv pip install -r brain\requirements.txt --python brain\.venv\Scripts\python.exe"
            if ($BrainOnly) { exit 1 }
        }
    } else {
        $BrainPython = $BrainVenv
    }
}

if (-not $BrainOnly) {
    # 1. Check node_modules
    $NodeModulesPath = "$AvatarDir\node_modules"
    if (-not (Test-Path $NodeModulesPath)) {
        Write-Host "[AVATAR] node_modules not found. Installing dependencies (npm install)..." -ForegroundColor Yellow
        npm --prefix $AvatarDir install
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install avatar dependencies. Run 'npm --prefix avatar install' manually."
            if ($AvatarOnly) { exit 1 }
        }
    }

    # 2. Check compiled dist (index.cjs)
    $AvatarMain = "$AvatarDir\dist\main\index.cjs"
    if (-not (Test-Path $AvatarMain)) {
        Write-Host "[AVATAR] Compiled dist/ not found. Building Electron bundle (npm run build:electron)..." -ForegroundColor Yellow
        npm --prefix $AvatarDir run build:electron
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to build avatar. Run 'npm --prefix avatar run build:electron' manually to inspect TypeScript errors."
            if ($AvatarOnly) { exit 1 }
        }
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
        param($root, $py)
        Set-Location $root
        & $py -m brain.main 2>&1 | ForEach-Object { "[BRAIN] $_" }
    } -ArgumentList $ProjectRoot, $BrainPython
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
Write-Host "Voice activation: Right Ctrl key (global hotkey)" -ForegroundColor Cyan
Write-Host "Health endpoint:  http://127.0.0.1:8766/health" -ForegroundColor Cyan
Write-Host "Chat endpoint:    http://127.0.0.1:8766/chat" -ForegroundColor Cyan
Write-Host ""

try {
    while ($true) {
        Start-Sleep -Milliseconds 500
        if ($brainJob)   { Receive-Job $brainJob   | Write-Host }
        if ($avatarJob)  { Receive-Job $avatarJob  | Write-Host }

        if ($brainJob -and ($brainJob.State -eq 'Completed' -or $brainJob.State -eq 'Failed')) {
            Write-Warning "[BRAIN] Process exited unexpectedly!"
            Receive-Job $brainJob | Write-Host
            foreach ($child in $brainJob.ChildJobs) {
                if ($child.JobStateInfo.State -eq 'Failed') {
                    Write-Error "[BRAIN ERROR] $($child.JobStateInfo.Reason.Message)"
                }
            }
            break
        }
        if ($avatarJob -and ($avatarJob.State -eq 'Completed' -or $avatarJob.State -eq 'Failed')) {
            Write-Warning "[AVATAR] Process exited unexpectedly!"
            Receive-Job $avatarJob | Write-Host
            foreach ($child in $avatarJob.ChildJobs) {
                if ($child.JobStateInfo.State -eq 'Failed') {
                    Write-Error "[AVATAR ERROR] $($child.JobStateInfo.Reason.Message)"
                }
            }
            break
        }
    }
} finally {
    Write-Host "" ; Write-Host "Stopping all processes..." -ForegroundColor Yellow
    if ($brainJob)  { Stop-Job $brainJob;  Remove-Job $brainJob  }
    if ($avatarJob) { Stop-Job $avatarJob; Remove-Job $avatarJob }
    Write-Host "Done." -ForegroundColor Green
}