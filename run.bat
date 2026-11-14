@echo off
title WoW Finish Macro
cd /d "%~dp0"

python -c "import PIL, numpy" 2>nul || (
    echo Installing dependencies...
    python -m pip install --user -r requirements.txt
)

python wow_finish_macro.py
echo.
pause
