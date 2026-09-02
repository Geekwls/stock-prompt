@echo off
chcp 65001 >nul
:: =================================================================
:: stock-prompt Skill 一键更新脚本 (Windows)
:: 拉取最新代码 -> 同步全局技能副本 -> 防漂移校验
:: =================================================================

set "REPO_DIR=%~dp0.."
cd /d "%REPO_DIR%"

echo 🔍 正在检查本地版本与远程 repository 状态...

for /f "delims=" %%a in ('git status --porcelain') do (
    echo ❌ 检测到尚未提交的本地修改。为避免覆盖你的自定义内容，本次更新已停止。
    echo    请先提交、暂存或备份这些修改，再重新运行更新脚本。
    pause
    exit /b 1
)

if exist "%REPO_DIR%\version.json" (
    for /f "tokens=2 delims=:," %%a in ('findstr /c:"latest" "%REPO_DIR%\version.json"') do (
        set "LOCAL_VER=%%~a"
    )
    echo 📌 本地当前版本: v%LOCAL_VER:~2,-1%
)

echo 🔄 正在从 GitHub (main 分支) 拉取最新 Skill 代码...

git pull --ff-only origin main

if not %ERRORLEVEL% EQU 0 (
    echo ❌ 更新失败，请检查网络设置或 Git 配置。
    pause
    exit /b 1
)

echo ✅ 成功更新至最新版本！
echo.
echo 🛠 正在同步技能到本机全局环境 (Antigravity / Gemini)...

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python scripts\install_skills.py
    python scripts\install_skills.py --check
    echo ✅ 全局技能副本已同步并通过一致性校验。
) else (
    echo [WARN] 未检测到 Python，跳过全局同步（仓库内技能已是最新）。
)

pause
