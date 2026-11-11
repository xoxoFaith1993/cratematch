@echo off
cd /d "%~dp0"
title CrateMatch problem reports
rem Shows new reports from the "Report a problem" button. Add --all to see every report.
python tools\read_reports.py %*
pause
