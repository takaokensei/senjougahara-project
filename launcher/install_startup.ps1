<#
.SYNOPSIS
    Registers Senjougahara to start at Windows logon via Scheduled Task.
.PARAMETER Uninstall
    Remove the scheduled task.
.EXAMPLE
    .\install_startup.ps1
    .\install_startup.ps1 -Uninstall
#>
[CmdletBinding()]
param([switch]$Uninstall)

$TaskName   = "SenjougaharaStartup"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$PythonExe  = (Get-Command python -ErrorAction SilentlyContinue)?.Source

if (-not $PythonExe) {
    Write-Error "Python not found in PATH. Install Python 3.11+ first."
    exit 1
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed '$TaskName'."
    exit 0
}

$Action   = New-ScheduledTaskAction -Execute $PythonExe -Argument "launcher\launcher.py" -WorkingDirectory $ProjectRoot
$Trigger  = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Delay = "PT15S"
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 24) -MultipleInstances IgnoreNew -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Starts Senjougahara AI companion at logon."

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null
Write-Host "Registered '$TaskName'. Senjougahara will start at next logon."
Write-Host "To remove: .\install_startup.ps1 -Uninstall"