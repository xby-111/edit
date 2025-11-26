# scripts/set_temp_env.ps1
# 设置临时目录环境变量，避免 PowerShell TEMP 权限问题
# 用法: .\scripts\set_temp_env.ps1; python scripts\check_db.py

# 获取脚本所在目录的父目录（项目根目录）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# 设置临时目录为项目目录下的 .tmp 文件夹
$TempDir = Join-Path $ProjectRoot ".tmp"

# 创建临时目录（如果不存在）
if (-not (Test-Path $TempDir)) {
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
}

# 设置环境变量（仅对当前 PowerShell 会话有效）
$env:TEMP = $TempDir
$env:TMP = $TempDir

Write-Host "临时目录已设置为: $TempDir" -ForegroundColor Green
Write-Host "TEMP=$env:TEMP" -ForegroundColor Cyan
Write-Host "TMP=$env:TMP" -ForegroundColor Cyan

