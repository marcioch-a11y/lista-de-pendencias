Set WshShell = CreateObject("WScript.Shell")
' Executa o script python em segundo plano de forma 100% invisível (sem janela preta de console)
WshShell.Run "pythonw main.py", 0, false
