param(
    [string]$TaskPrefix = "Sandy-Trading-AI",
    [string]$MailpitTime = "08:40",
    [string]$AuthTime = "08:45",
    [string]$StartTime = "08:55",
    [string]$USStartTime = "18:55",
    [string]$SummaryTime = "15:45",
    [string]$USSummaryTime = "02:05"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Register-SandyTask {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Time,
        [string]$ScriptArguments = "",
        [string[]]$DaysOfWeek = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    )

    $scriptCommand = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\$Script`""
    if ($ScriptArguments) {
        $scriptCommand = "$scriptCommand $ScriptArguments"
    }

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $scriptCommand
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DaysOfWeek -At $Time
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable
    Register-ScheduledTask `
        -TaskName "$TaskPrefix $Name" `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Sandy-Trading-AI $Name" `
        -Force | Out-Host
}

Register-SandyTask -Name "Start Mailpit" -Script "scripts\start_mailpit.ps1" -Time $MailpitTime
Register-SandyTask -Name "Zerodha Auth Assist" -Script "scripts\daily_zerodha_auth_assist.ps1" -Time $AuthTime
Register-SandyTask -Name "Start Shadow Stack" -Script "scripts\start_shadow_stack.ps1" -Time $StartTime
Register-SandyTask -Name "Start US Shadow Stack" -Script "scripts\start_shadow_stack.ps1" -Time $USStartTime
Register-SandyTask -Name "Daily Summary Email" -Script "scripts\daily_summary.ps1" -Time $SummaryTime -ScriptArguments "-SendEmail"
Register-SandyTask -Name "US Post-Market Summary Email" -Script "scripts\daily_summary.ps1" -Time $USSummaryTime -ScriptArguments "-SendEmail" -DaysOfWeek @("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

$oldDraftTask = "$TaskPrefix Daily Summary Draft"
if (Get-ScheduledTask -TaskName $oldDraftTask -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $oldDraftTask -Confirm:$false
}

Write-Host "Scheduled weekday tasks installed:"
Write-Host "- $TaskPrefix Start Mailpit at $MailpitTime"
Write-Host "- $TaskPrefix Zerodha Auth Assist at $AuthTime"
Write-Host "- $TaskPrefix Start Shadow Stack at $StartTime"
Write-Host "- $TaskPrefix Start US Shadow Stack at $USStartTime"
Write-Host "- $TaskPrefix Daily Summary Email at $SummaryTime"
Write-Host "- $TaskPrefix US Post-Market Summary Email at $USSummaryTime on Tuesday-Saturday"
Write-Host ""
Write-Host "Daily Summary Email sends through the configured SMTP target. With Mailpit defaults, it is captured locally at http://127.0.0.1:8025 and is not delivered to Gmail."
