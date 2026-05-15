@echo off
wsl bash -lc "cd \"$(wslpath '%~dp0')\" && ./rob.sh"
pause
