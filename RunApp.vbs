' Start BankDash (Flask on localhost:5050) in a hidden window.
' Running it again restarts the app instead of adding another copy: every python process
' running source/main.py, and whatever still listens on port 5050, is stopped first.
Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
AppDir = Fso.GetParentFolderName(WScript.ScriptFullName)

StopOld = "powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command """ & _
  "$ids = @(Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | " & _
  "Where-Object { $_.CommandLine -like '*source/main.py*' } | ForEach-Object { $_.ProcessId }) + " & _
  "@(Get-NetTCPConnection -LocalPort 5050 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }); " & _
  "$ids | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"""
WshShell.Run StopOld, 0, True

WshShell.Run "cmd /c cd /d """ & AppDir & """ && python source/main.py", 0, False
