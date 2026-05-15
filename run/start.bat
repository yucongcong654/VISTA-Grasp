@echo off
wsl bash -lc "cd \"$(wslpath '%~dp0')\" && ./start.sh"
pause
