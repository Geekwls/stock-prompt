@echo off
chcp 65001 >nul
:: =================================================================
:: stock-prompt Skill 一键更新脚本 (Windows)
:: 兼容入口：转交统一 Python 更新管理器
:: =================================================================

set "REPO_DIR=%~dp0.."
where python >nul 2>nul
if not errorlevel 1 (
    python "%REPO_DIR%\scripts\update_manager.py" apply --yes %*
    exit /b %errorlevel%
)
where python3 >nul 2>nul
if not errorlevel 1 (
    python3 "%REPO_DIR%\scripts\update_manager.py" apply --yes %*
    exit /b %errorlevel%
)
echo [ERR] 未检测到 Python。
exit /b 1
