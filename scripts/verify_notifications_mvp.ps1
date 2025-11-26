$ErrorActionPreference = "Stop"

function Write-Step($message) {
    Write-Host "==== $message" -ForegroundColor Cyan
}

function Ensure-Venv {
    $venvDir = ".venv"
    if (-not (Test-Path $venvDir)) {
        Write-Step "创建虚拟环境 $venvDir"
        python -m venv $venvDir
    }
    $activate = Join-Path $venvDir "Scripts/Activate.ps1"
    if (-not (Test-Path $activate)) {
        throw "未找到虚拟环境激活脚本：$activate"
    }
    Write-Step "激活虚拟环境"
    . $activate
}

function Check-Imports {
    Write-Step "检查关键模块是否已安装"
    $missing = python -c "import importlib.util;mods=['fastapi','pydantic','jose','uvicorn','py_opengauss','websockets'];print(','.join([m for m in mods if importlib.util.find_spec(m) is None]))"
    if ($missing) {
        $missing = $missing.Trim()
        if ($missing.Length -gt 0) {
            Write-Host "以下模块未安装或不在当前 venv： $missing" -ForegroundColor Yellow
        }
    }
    Write-Step "当前 pip list"
    python -m pip list
}

function Run-Cmd {
    param(
        [string]$cmd,
        [string[]]$args
    )
    Write-Step "$cmd $($args -join ' ')"
    & $cmd @args
    if ($LASTEXITCODE -ne 0) {
        throw "$cmd $($args -join ' ') 失败，退出码 $LASTEXITCODE"
    }
}

function Wait-Service {
    param(
        [string]$BaseUrl = "http://127.0.0.1:8000",
        [int]$Port = 8000,
        [int]$Retries = 20
    )
    Write-Step "等待服务可用 ($BaseUrl)"
    for ($i = 0; $i -lt $Retries; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/health" -TimeoutSec 3 -ErrorAction Stop
            if ($resp.StatusCode -ge 200) { return $true }
        } catch {
            try {
                $tcp = Test-NetConnection -ComputerName "127.0.0.1" -Port $Port
                if ($tcp.TcpTestSucceeded) { return $true }
            } catch { }
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

# 主流程
try {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    Set-Location (Join-Path $scriptDir "..")

    $baseUrl = if ($env:NOTIFY_BASE_URL) { $env:NOTIFY_BASE_URL } else { "http://127.0.0.1:8000" }
    $port = if ($env:NOTIFY_PORT) { [int]$env:NOTIFY_PORT } else { 8000 }

    Ensure-Venv

    Check-Imports

    Run-Cmd "python" @("-m", "compileall", "app")
    Run-Cmd "python" @("scripts/smoke_imports.py")
    Run-Cmd "python" @("scripts/check_db.py")

    Write-Step "后台启动 uvicorn"
    $logOut = "uvicorn.log"
    $logErr = "uvicorn.err.log"
    $proc = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$port" -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru -NoNewWindow
    $proc.Id | Out-File -FilePath "uvicorn.pid" -Encoding ascii

    $ready = Wait-Service -BaseUrl $baseUrl -Port $port
    if (-not $ready) {
        throw "服务未在预期时间内启动，请检查 $logErr"
    }

    Run-Cmd "python" @("scripts/test_notification_rest_flow.py")

    Write-Step "执行 WebSocket 验收"
    python scripts/ws_notifications_smoke.py
    if ($LASTEXITCODE -eq 2) {
        Write-Host "WS 验收被跳过（websockets 未安装）" -ForegroundColor Yellow
    } elseif ($LASTEXITCODE -ne 0) {
        throw "WS 验收失败，退出码 $LASTEXITCODE"
    }

    Write-Host "🎉 验收脚本执行完成" -ForegroundColor Green
    $global:exitCode = 0
} catch {
    Write-Host "💥 验收中断: $_" -ForegroundColor Red
    $global:exitCode = 1
} finally {
    if (Test-Path "uvicorn.pid") {
        try {
            $pid = Get-Content "uvicorn.pid" | Select-Object -First 1
            if ($pid) {
                Write-Step "停止 uvicorn (PID=$pid)"
                Stop-Process -Id $pid -ErrorAction SilentlyContinue
            }
        } catch {
            Write-Host "⚠️ 无法停止 uvicorn: $_" -ForegroundColor Yellow
        }
        Remove-Item "uvicorn.pid" -ErrorAction SilentlyContinue
    }
    try {
        $portCheck = netstat -ano | findstr :$port
        if ($portCheck) {
            Write-Host "⚠️ 端口 $port 仍在监听，请手动检查剩余进程。" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️ netstat 检查失败: $_" -ForegroundColor Yellow
    }
}

exit $global:exitCode
