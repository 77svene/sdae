@echo off
set PYTHONUNBUFFERED=1
cd /d C:\Users\ll-33\Projects\sdae
python test_score.py > C:\Users\ll-33\.sdae\test_score.log 2>&1
echo EXIT=%ERRORLEVEL% >> C:\Users\ll-33\.sdae\test_score.log
