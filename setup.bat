@echo off
REM Quick setup script for Crypto Trading Bot

echo ============================================================
echo CRYPTO TRADING BOT - QUICK SETUP
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

echo [1/4] Installing dependencies...
pip install -r requirements.txt

echo.
echo [2/4] Checking environment configuration...
if not exist ".env" (
    echo WARNING: .env file not found!
    echo Please copy .env.template to .env and add your API credentials.
    echo.
    copy .env.template .env
    echo Created .env file. Please edit it with your credentials.
    pause
    exit /b 1
)

echo.
echo [3/4] Testing API connection...
python cli.py test-api

echo.
echo [4/4] Setup complete!
echo.
echo ============================================================
echo NEXT STEPS:
echo ============================================================
echo 1. Edit .env file with your Robinhood API credentials
echo 2. Review config.py for trading parameters
echo 3. Start the bot: python cli.py start
echo.
echo COMMANDS:
echo   python cli.py start       - Start the trading bot
echo   python cli.py status      - Check bot status
echo   python cli.py history     - View trade history
echo   python cli.py signals     - View signal status
echo   python cli.py test-api    - Test API connection
echo.
echo ============================================================
pause
