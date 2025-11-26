# scripts/run_with_safe_temp.ps1
# 安全执行命令的包装脚本，自动设置临时目录
# 用法: .\scripts\run_with_safe_temp.ps1 python scripts\check_db.py

param(
    [Parameter(Mandatory=$true, ValueFromRemainingArguments=$true)]
    [string[]]$Command
)

# 获取脚本所在目录的父目录（项目根目录）
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

# 设置临时目录为项目目录下的 .tmp 文件夹
$tempDir = Join-Path $repoRoot ".tmp"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$env:TEMP = $tempDir
$env:TMP = $tempDir

# 执行命令（原样传递所有参数）
& $Command

# 返回真实退出码
exit $LASTEXITCODE
