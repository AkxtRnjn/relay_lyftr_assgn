@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
    echo Run run.cmd first in the folder containing your original chat database.
) else (
    "backend\.venv\Scripts\python.exe" "scripts\list_chats.py"
)
pause
