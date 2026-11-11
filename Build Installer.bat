@echo off
setlocal
cd /d "%~dp0"
title Build the CrateMatch installer
rem Builds dist\CrateMatch.exe and installer\Output\CrateMatchSetup.exe.
rem "Build Installer.bat quiet" skips the pause at the end (used by Publish Update.bat).

for /f %%v in ('python tools\version.py') do set "VER=%%v"
if not defined VER goto :fail
echo == CrateMatch %VER% ==

python -m pip install -q -r requirements.txt pyinstaller || goto :fail
python tools\make_icon.py || goto :fail

if not exist build mkdir build
python -c "import sys;v=sys.argv[1];t=open('tools/version_info.txt',encoding='utf-8').read().replace('{VERSION}',v).replace('{VTUPLE}',v.replace('.',', ')+', 0');open('build/version_info.txt','w',encoding='utf-8').write(t)" %VER% || goto :fail

python -m PyInstaller --noconfirm --clean --onefile --windowed --name CrateMatch ^
  --icon cratematch\assets\icon.ico --version-file build\version_info.txt ^
  --add-data "cratematch\assets;assets" --collect-all customtkinter ^
  run.py || goto :fail

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (echo Inno Setup not found: winget install JRSoftware.InnoSetup & goto :fail)
"%ISCC%" /Qp "/DAppVersion=%VER%" installer\CrateMatch.iss || goto :fail

echo.
echo Built installer\Output\CrateMatchSetup.exe (version %VER%)
if /i not "%~1"=="quiet" pause
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
if /i not "%~1"=="quiet" pause
exit /b 1
