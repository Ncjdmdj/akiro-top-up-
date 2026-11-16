@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
:loop
echo [%date% %time%] Starting bot...
python -m app.main
echo [%date% %time%] Bot stopped. Restarting in 5s... (Ctrl+C to quit)
timeout /t 5 >nul
goto loop
