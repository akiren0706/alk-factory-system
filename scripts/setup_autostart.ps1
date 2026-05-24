# ALK 自動インポート - 自動起動登録スクリプト
# このスクリプトを1回だけ実行すると、以降はPC起動・スリープ復帰時に自動で動きます

$taskName   = "ALK_AutoImport"
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$batFile    = Join-Path $scriptDir "start.bat"
$pythonw    = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source

# pythonw.exe のパスを探す
if (-not $pythonw) {
    $pythonw = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
}
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command python.exe -ErrorAction SilentlyContinue)?.Source
    if (-not $pythonw) {
        Write-Host "ERROR: Python が見つかりません。Python をインストールしてください。" -ForegroundColor Red
        pause
        exit 1
    }
    $pythonw = $pythonw -replace "python\.exe$", "pythonw.exe"
}

$pyScript = Join-Path $scriptDir "auto_import.py"

Write-Host "=== ALK 自動起動 登録 ===" -ForegroundColor Cyan
Write-Host "Python  : $pythonw"
Write-Host "スクリプト: $pyScript"
Write-Host "プロジェクト: $projectDir"
Write-Host ""

# 既存タスクを削除してから再登録
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# アクション定義
$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "`"$pyScript`"" `
    -WorkingDirectory $projectDir

# トリガー: ログオン時 + スリープ復帰時
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# スリープ復帰トリガー（イベントログ経由）
$triggerWake = New-ScheduledTaskTrigger -AtStartup
$triggerWake.Delay = "PT10S"   # 復帰後10秒待ってから起動

# 設定
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

# 登録
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($triggerLogon, $triggerWake) `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "✅ タスクスケジューラへの登録が完了しました！" -ForegroundColor Green
Write-Host ""
Write-Host "これ以降、以下のタイミングで自動起動します:" -ForegroundColor Yellow
Write-Host "  - PC起動・ログイン時"
Write-Host "  - スリープ復帰時（10秒後）"
Write-Host ""
Write-Host "今すぐ起動しますか？ (Y/N)" -ForegroundColor Cyan
$ans = Read-Host
if ($ans -match "^[Yy]") {
    Start-ScheduledTask -TaskName $taskName
    Write-Host "起動しました。" -ForegroundColor Green
}

pause
