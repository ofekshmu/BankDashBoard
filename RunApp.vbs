Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d ""C:\Users\ofeks\OneDrive\Ofek\BankProject"" && python source/main.py", 0, False
