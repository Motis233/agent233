# ===============================================================
# sync.ps1 —— 一键同步本地代码到GitHub
# ===============================================================
# 用法（三种任选）:
#   1. PowerShell里运行:  .\sync.ps1 "提交说明"(可选)
#   2. 双击 sync.bat（会自动调用本脚本）
#   3. 在项目目录:        powershell -File sync.ps1
#
# 行为:
#   - 检查是否有改动（含未跟踪的新文件），无改动则直接退出
#   - 拉取远程更新并合并（组员推了新代码时自动整合）
#   - 自动提交（说明未给时按改动文件自动生成）并推送

param([string]$Message = "")

Set-Location $PSScriptRoot

# ---- 0. 检查改动 ----
$status = git status --porcelain
if (-not $status) {
    Write-Host "[同步] 没有改动，本地与远程已是最新" -ForegroundColor Green
    exit 0
}
$changed = ($status | Measure-Object -Line).Lines
Write-Host "[同步] 检测到 $changed 处改动:" -ForegroundColor Cyan
$status | ForEach-Object { Write-Host "  $_" }

# ---- 1. 先拉远程（整合组员的提交，避免推送被拒）----
Write-Host "`n[同步] 拉取远程更新..." -ForegroundColor Cyan
git pull --rebase origin main 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "[同步] 拉取失败(可能有冲突)，请手动处理: git status" -ForegroundColor Red
    exit 1
}

# ---- 2. 生成提交说明 ----
if ($Message -eq "") {
    # 未指定说明时按改动文件类型自动生成
    $files = ($status | ForEach-Object { $_.Substring(3) })
    $py = ($files | Where-Object { $_ -match "\.py$" }).Count
    $Message = "更新: $changed 个文件"
    if ($py -gt 0) { $Message += "（含 $py 个Python文件）" }
    $Message += " - " + (($files | Select-Object -First 3) -join ", ")
    if ($changed -gt 3) { $Message += " 等" }
}

# ---- 3. 提交并推送 ----
Write-Host "`n[同步] 提交: $Message" -ForegroundColor Cyan
git add -A
git commit -m $Message 2>&1 | Out-Host

Write-Host "`n[同步] 推送到 GitHub..." -ForegroundColor Cyan
git push origin main 2>&1 | Out-Host
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[同步] 完成! https://github.com/mimimichen666/-" -ForegroundColor Green
} else {
    Write-Host "`n[同步] 推送失败，请检查网络或凭证" -ForegroundColor Red
    exit 1
}
