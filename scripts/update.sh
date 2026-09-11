#!/usr/bin/env bash

# =================================================================
# stock-prompt Skill 一键更新脚本 (Linux / macOS)
# 兼容入口：转交统一 Python 更新管理器
# =================================================================

set -e
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$REPO_DIR/scripts/update_manager.py" apply --yes "$@"
fi
exec python "$REPO_DIR/scripts/update_manager.py" apply --yes "$@"
