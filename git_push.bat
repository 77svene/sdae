@echo off
cd /d C:\Users\ll-33\Projects\sdae
git config user.email "201388040+77svene@users.noreply.github.com"
git config user.name "77svene"
git add -A
git commit -m "refactor: Windows compat fixes and self-upgrader engine"
git push origin main
echo PUSH_DONE
