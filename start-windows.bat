@echo off
setlocal EnableExtensions
title Finance Intelligence Studio - starting
cd /d "%~dp0"

echo ==============================================================
echo    Finance Intelligence Studio - one-click start (Windows)
echo ==============================================================
echo  This window installs anything missing, prepares the database,
echo  starts the app and opens it in your browser.
echo.

rem ---------------------------------------------------------------- 1. uv
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo [1/5] Installing uv - the Python package manager. It also downloads Python if needed...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  where uv >nul 2>nul
  if errorlevel 1 goto :fail_uv
) else (
  echo [1/5] uv is installed.
)

rem ---------------------------------------------------------------- 2. Node.js
set "PATH=%ProgramFiles%\nodejs;%PATH%"
where node >nul 2>nul
if errorlevel 1 (
  echo [2/5] Node.js not found. Installing it with winget - click Yes if Windows asks...
  winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
  where node >nul 2>nul
  if errorlevel 1 goto :fail_node
) else (
  echo [2/5] Node.js is installed.
)

rem ---------------------------------------------------------------- database choice
rem Uses PostgreSQL if backend\.env sets DATABASE_URL; otherwise a local database file.
set "OWN_DB="
if exist "backend\.env" findstr /b /i "DATABASE_URL" "backend\.env" >nul 2>nul && set "OWN_DB=1"
if not defined DATABASE_URL if not defined OWN_DB set "DATABASE_URL=sqlite:///storage/finance_studio.db"
if defined OWN_DB (
  echo        Database: PostgreSQL from backend\.env
) else (
  echo        Database: local file backend\storage\finance_studio.db
)

rem ---------------------------------------------------------------- 3-4. backend
echo [3/5] Installing backend packages. The first time takes a few minutes...
pushd backend
uv sync
if errorlevel 1 goto :fail_backend
echo [4/5] Preparing the database...
uv run alembic upgrade head
if errorlevel 1 goto :fail_db
popd

rem ---------------------------------------------------------------- 5. frontend
rem A marker file is written only after a complete install, so an interrupted download
rem is never mistaken for a finished one.
pushd frontend
if exist "node_modules\.fis-installed" (
  echo [5/5] Website packages are installed.
) else (
  call :npm_install
  if errorlevel 1 goto :fail_frontend
)
popd

rem ---------------------------------------------------------------- start
rem An older copy that is still running would keep ports 8000/5173 and answer instead of this one.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-old-copy.ps1"
if errorlevel 2 goto :end
echo.
echo Starting the app. Two new windows will open - keep them open while you use the app.
start "Finance Studio - BACKEND (keep open)" /D "%~dp0backend" cmd /k uv run uvicorn app.main:app --port 8000
start "Finance Studio - WEBSITE (keep open)" /D "%~dp0frontend" cmd /k npm run dev
echo Waiting for the app to be ready...
powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){ try { Invoke-WebRequest -UseBasicParsing 'http://localhost:8000/api/health' -TimeoutSec 2 | Out-Null; try { Invoke-WebRequest -UseBasicParsing 'http://localhost:5173' -TimeoutSec 2 | Out-Null; exit 0 } catch {} } catch {}; Start-Sleep 1 }; exit 1"
if errorlevel 1 (
  echo The app is taking longer than usual. Check the two new windows for error messages.
)
start "" http://localhost:5173
echo.
echo ==============================================================
echo  Done! The app is at http://localhost:5173
echo  First time? Click "Create an account".
echo  To stop the app, close the BACKEND and WEBSITE windows.
echo ==============================================================
pause
exit /b 0

rem ---------------------------------------------------------------- npm install with retries
:npm_install
set /a NPM_TRY=0
:npm_retry
set /a NPM_TRY+=1
echo [5/5] Installing website packages - attempt %NPM_TRY% of 4. The first time takes a few minutes...
call npm install
if not errorlevel 1 (
  echo ok> "node_modules\.fis-installed"
  exit /b 0
)
if %NPM_TRY% GEQ 4 exit /b 1
echo.
echo The internet connection dropped during the download. Retrying in 15 seconds...
timeout /t 15 /nobreak >nul
goto :npm_retry

:fail_uv
echo.
echo Could not install uv. Close this window, restart the computer, and double-click this file again.
goto :end
:fail_node
echo.
echo Could not install Node.js automatically.
echo Please install the LTS version from https://nodejs.org, then double-click this file again.
goto :end
:fail_backend
echo.
echo Installing the backend packages failed. Check your internet connection and try again.
goto :end
:fail_db
echo.
echo Preparing the database failed. If you set DATABASE_URL in backend\.env, check PostgreSQL is running.
goto :end
:fail_frontend
echo.
echo Installing the website packages failed after 4 attempts because the internet connection kept dropping.
echo Try this: switch to a different network, e.g. your phone's hotspot; pause any VPN;
echo then double-click this file again. It continues where it stopped.
goto :end
:end
echo If this keeps happening, send a screenshot of this window.
pause
exit /b 1
