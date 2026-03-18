@echo off
REM Build and push Runpod Docker image
REM Usage: build-runpod.cmd [version_tag]
REM Example: build-runpod.cmd v1.0.1

set VERSION_TAG=%~1
if "%VERSION_TAG%"=="" set VERSION_TAG=v1.0.1

echo Building apertso/xtts-runpod:%VERSION_TAG%
echo.

REM Build the image
docker build -f Dockerfile.runpod -t apertso/xtts-runpod:%VERSION_TAG% -t apertso/xtts-runpod:latest .
if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

echo.
echo Build successful!
echo.

REM Push to Docker Hub
echo Pushing apertso/xtts-runpod:%VERSION_TAG% to Docker Hub...
docker push apertso/xtts-runpod:%VERSION_TAG%
if errorlevel 1 (
    echo Push failed!
    exit /b 1
)

echo.
echo Pushing apertso/xtts-runpod:latest to Docker Hub...
docker push apertso/xtts-runpod:latest

echo.
echo Done! Image pushed: apertso/xtts-runpod:%VERSION_TAG%
