@echo off
setlocal enabledelayedexpansion
chcp 437 >nul

echo Testing script execution...
set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOGDIR=D:\Projects\edit\.tmp\test_logs_%TIMESTAMP%

mkdir "%LOGDIR%" 2>nul
echo Log directory created: %LOGDIR% > "%LOGDIR%\test.log"

echo Testing DB connectivity pre-check...
powershell -Command "try { $tcp = New-Object System.Net.Sockets.TcpClient; $tcp.Connect('120.46.143.126', 5432); $tcp.Close(); Write-Output 'TCP_CONNECTED' } catch { Write-Output 'TCP_FAILED' }" > "%LOGDIR%\db_probe.txt" 2>nul

set /p DB_PROBE_RESULT=<"%LOGDIR%\db_probe.txt"
echo DB Probe Result: %DB_PROBE_RESULT%

if not "%DB_PROBE_RESULT%"=="TCP_CONNECTED" (
    set RESULT=FAIL
    set FAIL_REASON=DB_UNREACHABLE
) else (
    set RESULT=PASS
    set FAIL_REASON=NONE
)

echo.
echo RESULT=%RESULT%
echo FAIL_REASON=%FAIL_REASON%
echo LOGDIR=%LOGDIR%

exit /b 0