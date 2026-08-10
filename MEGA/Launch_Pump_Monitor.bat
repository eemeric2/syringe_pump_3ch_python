@echo off
title 3-Channel Syringe Pump Monitor
cd /d "%~dp0"
echo ========================================
echo   3-Channel Syringe Pump Monitor
echo ========================================
echo.
echo Starting GUI...
echo.
python syringe_pump_3ch_MEGA_monitor.py
if errorlevel 1 (
    echo.
    echo ========================================
    echo   ERROR: Failed to start monitor
    echo ========================================
    echo.
    echo Possible issues:
    echo   - Python not installed or not in PATH
    echo   - Missing libraries (tkinter, pyserial)
    echo   - Script file not found
    echo.
    pause
) else (
    echo.
    echo Monitor closed successfully.
)