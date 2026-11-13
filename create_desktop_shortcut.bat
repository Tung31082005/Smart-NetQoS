@echo off
set SCRIPT="%TEMP%\CreateShortcut.vbs"
set APP_DIR=%~dp0
set LAUNCHER=%APP_DIR%launcher.vbs
set ICON=%APP_DIR%assets\icon.ico

echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
echo sLinkFile = oWS.SpecialFolders("Desktop") ^& "\Smart NetQoS Manager.lnk" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "wscript.exe" >> %SCRIPT%
echo oLink.Arguments = """%LAUNCHER%""" >> %SCRIPT%
echo oLink.WorkingDirectory = "%APP_DIR%" >> %SCRIPT%
echo oLink.Description = "Smart NetQoS Manager - Giam Sat va Phan Luong Mang Thong Minh" >> %SCRIPT%
echo oLink.IconLocation = "%ICON%,0" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%

cscript /nologo %SCRIPT%
del %SCRIPT%
echo [OK] Da tao phim tat 'Smart NetQoS Manager' tren man hinh Desktop thanh cong!
pause
