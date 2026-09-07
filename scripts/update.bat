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

git fetch origin main
if errorlevel 1 (
    echo ❌ 无法连接远程仓库，请检查网络设置或 Git 配置。
    pause
    exit /b 1
)

for /f %%a in ('git rev-parse HEAD') do set "LOCAL_HASH=%%a"
for /f %%a in ('git rev-parse origin/main') do set "REMOTE_HASH=%%a"

if "%LOCAL_HASH%"=="%REMOTE_HASH%" goto up_to_date

git pull --ff-only origin main
if errorlevel 1 (
    echo ❌ 拉取失败，请检查网络设置或 Git 配置。
    pause
    exit /b 1
)

if exist "%REPO_DIR%\version.json" (
    for /f "tokens=2 delims=:," %%a in ('findstr /c:"latest" "%REPO_DIR%\version.json"') do (
        set "NEW_VER=%%~a"
    )
    echo 🎉 成功更新至最新版本: v%NEW_VER:~2,-1%！
) else (
    echo 🎉 成功更新至最新版本！
)
goto sync_skills

:up_to_date
echo ✅ 本地 stock-prompt 技能库已经是最新版！

:sync_skills
echo.
echo 🛠 正在同步技能到本机全局环境 (Gemini / Antigravity / Codex)...

set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD (
    where python3 >nul 2>nul && set "PY_CMD=python3"
)

if defined PY_CMD (
    %PY_CMD% scripts\install_skills.py
    if errorlevel 1 goto install_failed
    %PY_CMD% scripts\install_skills.py --check
    if errorlevel 1 goto install_failed
    echo ✅ 全局技能副本已同步并通过一致性校验。
    goto done
) else (
    echo [WARN] 未检测到 Python，跳过全局同步（仓库内技能已是最新）。
    goto done
)

:install_failed
echo [WARN] 全局同步未完全成功，可稍后手动运行: python scripts\install_skills.py

:done
pause
