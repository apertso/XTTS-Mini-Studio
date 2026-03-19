@echo off
setlocal
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
start "" /B python -m tts
echo TTS Server started from %CD% on http://localhost:5000
pause
exit /b 0
