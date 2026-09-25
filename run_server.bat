@echo off
title Universal OCR Microservice
cd /d "%~dp0"
echo ===================================================
echo Starting Universal Document OCR Server...
echo Web Viewer: http://127.0.0.1:8000/viewer
echo API Docs:   http://127.0.0.1:8000/docs
echo ===================================================
call .\venv\Scripts\activate.bat
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
