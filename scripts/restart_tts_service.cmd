@echo off
setlocal

set "SERVICE_NAME=XTTS-TTS"
if not "%~1"=="" set "SERVICE_NAME=%~1"

echo Restarting Windows service "%SERVICE_NAME%"...
net stop "%SERVICE_NAME%"
if errorlevel 1 exit /b %errorlevel%

net start "%SERVICE_NAME%"
if errorlevel 1 exit /b %errorlevel%

echo Done.
exit /b 0
