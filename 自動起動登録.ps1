# ALK工場停止管理システム - Windowsログイン時自動起動登録
# このスクリプトを右クリック→「PowerShellで実行」してください

$ErrorActionPreference = "Stop"

$appDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$vbsPath   = Join-Path $appDir "バックグラウンド起動.vbs"
$taskName  = "ALK工場停止管理システム"

Write-Host "=== ALK工場停止管理システム 自動起動登録 ===" -ForegroundColor Cyan

# 既存タスクを削除
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# アクション：wscript.exe でVBSを実行（ウィンドウなし）
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$vbsPath`""

# トリガー：ログイン時（現在のユーザー）
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# 設定：電源・バッテリー無関係に実行
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

# 登録
Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "✅ タスク登録完了！次回Windowsログイン時から自動起動します。" -ForegroundColor Green
Write-Host ""
Write-Host "今すぐ起動する場合は「バックグラウンド起動.vbs」をダブルクリックしてください。" -ForegroundColor Yellow
Write-Host ""
Write-Host "自動起動を解除する場合はタスクスケジューラで「$taskName」を削除してください。"
Write-Host ""
Read-Host "Enterキーで閉じる"
