@echo off
setlocal
pushd "%~dp0"
start "" /min "C:\Users\chris\AppData\Local\Programs\Python\Python313\python.exe" "%CD%\strategy_platform_server.py" --port 4174
start "" "http://localhost:4174/index.html"
popd
