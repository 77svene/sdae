@echo off
cd /d C:\Users\ll-33\Projects\sdae
git config user.email "201388040+77svene@users.noreply.github.com"
git config user.name "77svene"
git add -A
git commit -m "fix: Qwen3 no_think, single-pass scorer, Windows disk path, self-upgrader"
git push origin main
echo GIT_DONE
