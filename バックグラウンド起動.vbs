Dim fso, objShell
Set fso      = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

Dim appDir
appDir = fso.GetParentFolderName(WScript.ScriptFullName)

Dim pythonPath
pythonPath = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\python.exe"

' ポート8501の旧プロセスを停止（PowerShell経由・確実）
Dim killCmd
killCmd = "powershell -NoProfile -WindowStyle Hidden -Command """ & _
    "$c = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue;" & _
    "if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue };" & _
    "Start-Sleep -Milliseconds 800" & _
    """"
objShell.Run killCmd, 0, True

' Python を直接バックグラウンドで起動（cmd/Terminalウィンドウ不要）
objShell.CurrentDirectory = appDir
Dim startCmd
startCmd = """" & pythonPath & """ -m streamlit run """ & appDir & "\app.py"" " & _
           "--server.port 8501 --browser.gatherUsageStats false " & _
           "--server.headless true"
objShell.Run startCmd, 0, False

' ブラウザを開く（起動待ち）
WScript.Sleep 3500
objShell.Run "http://localhost:8501", 1, False
