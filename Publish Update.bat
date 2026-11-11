@echo off
setlocal
cd /d "%~dp0"
title Publish a CrateMatch update
rem Raises the version by one, builds the installer, saves the code to GitHub and uploads
rem the installer as a release. Every installed CrateMatch picks it up the next time it opens.

set /p "NOTES=What changed (one line, Enter to skip): "
if not defined NOTES set "NOTES=Fixes and improvements."

for /f %%v in ('python tools\version.py --bump') do set "VER=%%v"
if not defined VER goto :fail
echo Publishing v%VER%...

call "%~dp0Build Installer.bat" quiet || goto :fail

git add -A && git commit -q -m "v%VER%: %NOTES%" && git push -q || goto :fail

gh release create "v%VER%" "installer\Output\CrateMatchSetup.exe" --repo xoxoFaith1993/cratematch ^
   --title "CrateMatch v%VER%" --notes "%NOTES%" || goto :fail

echo.
echo Published v%VER%. Installed copies update the next time they open.
pause
exit /b 0

:fail
echo.
echo Publishing failed - see the messages above.
pause
exit /b 1
