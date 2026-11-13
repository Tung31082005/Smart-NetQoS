@echo off
:: Batch launcher for Smart NetQoS Manager
:: Requests Administrator once to allow live NetQosPolicy modifications
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Run silently with pythonw (no terminal window)
start "" pythonw.exe app.py
exit
