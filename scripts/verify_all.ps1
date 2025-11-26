# scripts/verify_all.ps1
# 一键验证脚本，自动设置临时目录并执行所有验证步骤

# 统一计算项目根目录（不依赖 $PWD）
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

# 强制设置临时目录
$tempDir = Join-Path $repoRoot ".tmp"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$env:TEMP = $tempDir
$env:TMP = $tempDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "通知MVP验证脚本" -ForegroundColor Green
Write-Host "项目根目录: $repoRoot" -ForegroundColor Cyan
Write-Host "临时目录: $tempDir" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 端口 8000 占用检查（安全模式：只允许停止本项目uvicorn进程）
$portInUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "⚠️  端口 8000 已被占用，检查占用进程..." -ForegroundColor Yellow
    
    $portInUse | ForEach-Object {
        $pid = $_.OwningProcess
        try {
            # 使用 Get-CimInstance 读取 CommandLine（兼容 PowerShell 5.1）
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction SilentlyContinue
            if ($proc) {
                $cmdLine = $proc.CommandLine
                $procName = $proc.Name
                
                # 只有当 CommandLine 同时包含 uvicorn 和 app.main:app 时才允许停止
                if ($cmdLine -and $cmdLine -like "*uvicorn*" -and $cmdLine -like "*app.main:app*") {
                    Write-Host "    停止本项目uvicorn进程 (PID: $pid)" -ForegroundColor Gray
                    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                } else {
                    Write-Host "❌ 端口 8000 被其他程序占用:" -ForegroundColor Red
                    Write-Host "    PID: $pid" -ForegroundColor Red
                    Write-Host "    进程名: $procName" -ForegroundColor Red
                    Write-Host "    命令行: $cmdLine" -ForegroundColor Red
                    Write-Host ""
                    Write-Host "请手动释放端口 8000 后重试" -ForegroundColor Yellow
                    exit 1
                }
            } else {
                Write-Host "    无法读取进程信息 (PID: $pid)，尝试停止..." -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        } catch {
            Write-Host "    检查进程时出错 (PID: $pid): $_" -ForegroundColor Yellow
        }
    }
    
    Start-Sleep -Seconds 2
}

# [1/3] 数据库自检
Write-Host "[1/3] 数据库自检..." -ForegroundColor Yellow
Set-Location $repoRoot
python scripts\check_db.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 数据库自检失败，退出码: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "✅ 数据库自检通过" -ForegroundColor Green
Write-Host ""

# [2/3] 启动 uvicorn（后台 + 日志）
Write-Host "[2/3] 启动 uvicorn 服务..." -ForegroundColor Yellow
Set-Location $repoRoot
$uvicornLog = Join-Path $repoRoot "uvicorn.log"
$uvicornErrLog = Join-Path $repoRoot "uvicorn.err.log"

# 启动 uvicorn（Start-Process 会继承当前会话的环境变量，所以 TEMP/TMP 已生效）
$uvicornProcess = Start-Process -FilePath "python" `
    -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $uvicornLog `
    -RedirectStandardError $uvicornErrLog `
    -WindowStyle Hidden `
    -PassThru

$uvicornPid = $uvicornProcess.Id

# 等待服务可用（轮询，最多 10 秒）
Write-Host "等待服务启动 (PID: $uvicornPid)..." -ForegroundColor Cyan
$maxWait = 10
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Host "✅ 服务已启动" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 1
        $waited++
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
}

if ($waited -ge $maxWait) {
    Write-Host ""
    Write-Host "❌ 服务启动超时" -ForegroundColor Red
    if (Test-Path $uvicornErrLog) {
        Write-Host "错误日志片段 (最后80行):" -ForegroundColor Yellow
        Get-Content $uvicornErrLog -Tail 80
    }
    Stop-Process -Id $uvicornPid -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host ""

# [3/3] 通知 MVP 验证
Write-Host "[3/3] 运行通知MVP验证..." -ForegroundColor Yellow
Set-Location $repoRoot
python scripts\verify_notifications_mvp.py
$verifyExitCode = $LASTEXITCODE

# 停止 uvicorn
Write-Host ""
Write-Host "停止 uvicorn 服务 (PID: $uvicornPid)..." -ForegroundColor Cyan
Stop-Process -Id $uvicornPid -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1  # 等待日志写入完成

# 检查日志关键字
Write-Host ""
Write-Host "检查日志中是否有 percent-placeholder 语法错误..." -ForegroundColor Cyan
$hasError = $false
if (Test-Path $uvicornErrLog) {
    $errorLines = Select-String -Path $uvicornErrLog -Pattern 'syntax error at or near "%"|CODE: 42601|username = %s' -ErrorAction SilentlyContinue
    if ($errorLines) {
        Write-Host "❌ 发现 percent-placeholder 语法错误在日志中" -ForegroundColor Red
        $errorLines | Select-Object -First 10 | ForEach-Object {
            Write-Host "    行 $($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red
        }
        $hasError = $true
    } else {
        Write-Host "✅ 未发现 percent-placeholder 语法错误" -ForegroundColor Green
    }
} else {
    Write-Host "⚠️  错误日志文件不存在: $uvicornErrLog" -ForegroundColor Yellow
}

# 最终输出
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($hasError) {
    Write-Host "❌ 验证失败：发现 percent-placeholder 语法错误" -ForegroundColor Red
    exit 1
} elseif ($verifyExitCode -eq 0) {
    Write-Host "✅ 所有验证通过！" -ForegroundColor Green
    exit 0
} else {
    Write-Host "❌ 验证失败，退出码: $verifyExitCode" -ForegroundColor Red
    exit $verifyExitCode
}
