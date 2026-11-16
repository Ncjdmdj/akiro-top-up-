@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.12 and tick "Add to PATH".
  pause
  exit /b 1
)

if not exist .env (
  copy .env.example .env >nul
  echo [OK] Created .env - edit it before running run.bat
)

if not exist venv (
  python -m venv venv
  if errorlevel 1 (
    echo [ERROR] Could not create venv
    pause
    exit /b 1
  )
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed
  pause
  exit /b 1
)

echo.
echo [INFO] Creating database...
where mysql >nul 2>nul
if errorlevel 1 (
  echo [WARN] mysql not found. Open Laragon - Database - HeidiSQL, then run laragon_setup.sql manually.
) else (
  mysql -u root < laragon_setup.sql
  if errorlevel 1 (
    echo [WARN] SQL import failed. Run laragon_setup.sql manually in HeidiSQL.
  ) else (
    echo [OK] Database ready
  )
)

echo.
echo Done. Next: edit .env, then run run.bat
pause
