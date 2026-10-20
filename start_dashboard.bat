@echo off
cd /d %~dp0
uv run python scripts\serve.py 8088
pause
