@echo off
REM Build and push Runpod Docker image
REM Usage: build-runpod.cmd [version_tag]
REM Example: build-runpod.cmd v1.0.1

set "DOCKER_REPO=apertso/xtts-runpod"
set "VERSION_TAG=%~1"
set "AUTO_TAG=0"

if "%VERSION_TAG%"=="" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $repo='%DOCKER_REPO%'; $url='https://hub.docker.com/v2/repositories/' + $repo + '/tags?page_size=100'; $allTags=@(); while ($url) { $response = Invoke-RestMethod -Uri $url -Method Get; if ($response.results) { $allTags += $response.results }; $url = $response.next }; $latest = $allTags | ForEach-Object { if ($_.name -match '^v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)$') { [PSCustomObject]@{ Major=[int]$Matches.major; Minor=[int]$Matches.minor; Patch=[int]$Matches.patch } } } | Sort-Object Major, Minor, Patch -Descending | Select-Object -First 1; if ($null -eq $latest) { 'v1.0.1' } else { 'v{0}.{1}.{2}' -f $latest.Major, $latest.Minor, ($latest.Patch + 1) }"` ) do set "VERSION_TAG=%%I"
    if not defined VERSION_TAG (
        echo Failed to resolve VERSION_TAG from Docker Hub.
        exit /b 1
    )
    set "AUTO_TAG=1"
)

if "%AUTO_TAG%"=="1" (
    echo Auto VERSION_TAG resolved to %VERSION_TAG%
)

echo Building %DOCKER_REPO%:%VERSION_TAG%
echo.

REM Build the image
docker build -f Dockerfile.runpod -t %DOCKER_REPO%:%VERSION_TAG% -t %DOCKER_REPO%:latest .
if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

echo.
echo Build successful!
echo.

REM Push to Docker Hub
echo Pushing %DOCKER_REPO%:%VERSION_TAG% to Docker Hub...
docker push %DOCKER_REPO%:%VERSION_TAG%
if errorlevel 1 (
    echo Push failed!
    exit /b 1
)

echo.
echo Pushing %DOCKER_REPO%:latest to Docker Hub...
docker push %DOCKER_REPO%:latest

echo.
echo Done! Image pushed: %DOCKER_REPO%:%VERSION_TAG%
