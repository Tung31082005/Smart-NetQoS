Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

args = ""
For i = 0 to WScript.Arguments.Count - 1
    args = args & " " & WScript.Arguments(i)
Next

WshShell.CurrentDirectory = currentDir
WshShell.Run "pythonw.exe """ & currentDir & "\app.py""" & args, 0, False
