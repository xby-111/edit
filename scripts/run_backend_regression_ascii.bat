@echo off
setlocal enabledelayedexpansion

rem Create log directory with timestamp
for /f %%p in ('python -c "import datetime,pathlib; p=pathlib.Path('.tmp')/('regression_logs_'+datetime.datetime.now().strftime('%%Y%%m%%d_%%H%%M%%S')); p.mkdir(parents=True, exist_ok=True); print(p)"') do set LOG_DIR=%%p

set RESULT=PASS
set FAIL_REASON=

echo Logs will be stored in %LOG_DIR%

rem Find available port 8001-8005
> "%LOG_DIR%\find_port_temp.py" echo import socket
>> "%LOG_DIR%\find_port_temp.py" echo port=None
>> "%LOG_DIR%\find_port_temp.py" echo for p in range(8001,8006):
>> "%LOG_DIR%\find_port_temp.py" echo ^    s=socket.socket()
>> "%LOG_DIR%\find_port_temp.py" echo ^    try:
>> "%LOG_DIR%\find_port_temp.py" echo ^        s.bind(('127.0.0.1',p))
>> "%LOG_DIR%\find_port_temp.py" echo ^        s.close()
>> "%LOG_DIR%\find_port_temp.py" echo ^        port=p
>> "%LOG_DIR%\find_port_temp.py" echo ^        break
>> "%LOG_DIR%\find_port_temp.py" echo ^    except OSError:
>> "%LOG_DIR%\find_port_temp.py" echo ^        s.close()
>> "%LOG_DIR%\find_port_temp.py" echo print(port or 8001)

for /f %%p in ('python "%LOG_DIR%\find_port_temp.py"') do set PORT=%%p
if "%PORT%"=="" set PORT=8001
del "%LOG_DIR%\find_port_temp.py"

echo Selected port %PORT%>"%LOG_DIR%\port.txt"

rem Start uvicorn in background (start /b) and record PID
start /b "" cmd /c "python -c ""import subprocess,pathlib; import sys; log_dir=r'%LOG_DIR%'; port=r'%PORT%'; log_file=pathlib.Path(log_dir)/'uvicorn.log'; p=subprocess.Popen(['python','-m','uvicorn','app.main:app','--host','0.0.0.0','--port',port], stdout=open(log_file,'w'), stderr=subprocess.STDOUT); (pathlib.Path(log_dir)/'uvicorn.pid').write_text(str(p.pid))"""
python -c "import time; time.sleep(5)"

rem Run database checks
python scripts/check_db.py >"%LOG_DIR%\check_db.log" 2>&1
if %ERRORLEVEL% NEQ 0 (
    if not "%RESULT%"=="FAIL" set RESULT=FAIL
    if "%FAIL_REASON%"=="" set FAIL_REASON=check_db
)

rem Run system admin verification if present
if exist scripts\verify_system_admin_mvp.py (
    python scripts/verify_system_admin_mvp.py >"%LOG_DIR%\verify_system_admin_mvp.log" 2>&1
    if %ERRORLEVEL% NEQ 0 (
        if not "%RESULT%"=="FAIL" set RESULT=FAIL
        if "%FAIL_REASON%"=="" set FAIL_REASON=verify_system_admin_mvp
    )
)

rem Run backend smoke for new features
python scripts/verify_backend_smoke.py >"%LOG_DIR%\verify_backend_smoke.log" 2>&1
if %ERRORLEVEL% NEQ 0 (
    if not "%RESULT%"=="FAIL" set RESULT=FAIL
    if "%FAIL_REASON%"=="" set FAIL_REASON=verify_backend_smoke
)

rem Stop uvicorn
if exist "%LOG_DIR%\uvicorn.pid" (
    for /f %%p in ('type "%LOG_DIR%\uvicorn.pid"') do set UVICORN_PID=%%p
    if not "%UVICORN_PID%"=="" taskkill /F /PID %UVICORN_PID% >nul 2>&1
)

rem Write summary files
python -c "import json,os,sys,pathlib; log_dir=pathlib.Path(sys.argv[1]); summary={'result': os.environ.get('RESULT','PASS'), 'fail_reason': os.environ.get('FAIL_REASON',''), 'log_dir': str(log_dir)}; json.dump(summary, open(log_dir/'summary.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)" "%LOG_DIR%"
echo RESULT=%RESULT% >"%LOG_DIR%\result.txt"
echo FAIL_REASON=%FAIL_REASON% >>"%LOG_DIR%\result.txt"

rem Zip logs
for /f %%z in ('python -c "import zipfile,pathlib,sys; log_dir=pathlib.Path(sys.argv[1]); zip_path=log_dir.with_suffix('.zip');\
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:\
    [z.write(p, p.relative_to(log_dir.parent)) for p in log_dir.rglob('*')];\
print(zip_path)" "%LOG_DIR%"') do set ZIP_FILE=%%z
echo ZIP=%ZIP_FILE%>>"%LOG_DIR%\result.txt"

echo Completed with %RESULT%. Logs: %LOG_DIR%
endlocal
