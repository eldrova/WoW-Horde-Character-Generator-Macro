#!/bin/bash
# Double-click to start the WoW Finish macro (macOS replacement for run.bat).
cd "$(dirname "$0")" || exit 1
printf '\033]0;WoW Finish Macro\007'

if [ ! -x .venv/bin/python ]; then
    echo "Creating Python environment..."
    /usr/bin/python3 -m venv .venv || { echo "Python 3 not found. Run: xcode-select --install"; read -r -p "Press Enter to close."; exit 1; }
fi
if ! .venv/bin/python -c "import PIL, numpy, Quartz, ApplicationServices" 2>/dev/null; then
    echo "Installing dependencies..."
    .venv/bin/python -m pip install -q --upgrade pip
    .venv/bin/python -m pip install -q -r requirements.txt
fi

.venv/bin/python wow_finish_macro.py "$@"
echo
read -r -p "Press Enter to close."
