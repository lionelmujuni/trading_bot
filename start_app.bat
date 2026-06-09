@echo off
title AlgoTrader

echo Starting FastAPI server...
start "FastAPI" cmd /k "cd /d %~dp0 && uvicorn api.api_server:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 >nul

echo Starting React dev server...
start "React" cmd /k "cd /d %~dp0react-app && npm run dev"

echo.
echo ================================================================
echo  AlgoTrader is starting up!
echo  FastAPI: http://localhost:8000
echo  React:   http://localhost:5173
echo ================================================================
echo.
echo Both windows will open automatically.
echo Close this window at any time — servers keep running in their own windows.
pause
