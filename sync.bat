@echo off
REM sync.bat —— 双击一键同步到GitHub（自动调用sync.ps1）
REM 说明: -ExecutionPolicy Bypass 绕过脚本执行限制，仅对本脚本生效

REM 有命令行参数就透传（如: sync.bat "修复了检索bug"）
powershell -ExecutionPolicy Bypass -File "%~dp0sync.ps1" %*
pause
