@echo off
setlocal
cd /d "%~dp0"
start "策略指引平台" /min "C:\Users\chris\AppData\Local\Programs\Python\Python313\python.exe" strategy_platform_server.py --port 4174
start "" "http://localhost:4174/index.html"
