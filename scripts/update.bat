@echo off
chcp 65001 >nul
:: =================================================================
:: stock-prompt Skill 一键同步与版本检查脚本 (Windows)
:: =================================================================

set "REPO_DIR=%~dp0.."
cd /d "%REPO_DIR%"

echo 🔍 正在检查本地版本与远程 repository 状态...

if exist "%REPO_DIR%\version.json" (
    for /f "tokens=2 delims=:," %%a in ('findstr /c:"latest" "%REPO_DIR%\version.json"') do (
        set "LOCAL_VER=%%~a"
    )
    echo 📌 本地当前版本: v%LOCAL_VER:~2,-1%
)

echo 🔄 正在从 GitHub (main 分支) 拉取最新 Skill 代码...

git pull origin main

if %ERRORLEVEL% EQU 0 (
    echo ✅ 成功更新至最新版本！
) else (
    echo ❌ 更新失败，请检查网络设置或 Git 配置。
)

pause
