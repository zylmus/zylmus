@echo off
chcp 65001 >nul
echo Uruchamianie Zylmus...
call .venv\Scripts\activate.bat
start "" "http://localhost:8000"
uvicorn backend.main:app --port 8000
