@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Khoi dong Mai Tam Translate...

start "Backend (FastAPI :8000)" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && uvicorn app.main:app --reload --port 8000"

start "Frontend (Vite :5173)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Da mo 2 cua so: Backend (http://localhost:8000) va Frontend (http://localhost:5173)
echo Dong cua so nay khong tat 2 server tren.
pause
