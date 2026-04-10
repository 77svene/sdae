@echo off
set PYTHONUNBUFFERED=1
cd /d C:\Users\ll-33\Projects\sdae
python main.py --daemon >> C:\Users\ll-33\.sdae\logs\daemon.log 2>&1
