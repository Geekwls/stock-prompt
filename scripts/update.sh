#!/usr/bin/env bash

# =================================================================
# stock-prompt Skill 一键同步与版本检查脚本 (Linux / macOS)
# =================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "🔍 正在检查本地版本与远程 repository 状态..."

if [ -f "$REPO_DIR/version.json" ]; then
    LOCAL_VER=$(grep -o '"latest": "[^"]*"' "$REPO_DIR/version.json" | cut -d'"' -f4)
    echo "📌 本地当前版本: v${LOCAL_VER}"
fi

echo "🔄 正在从 GitHub (main 分支) 拉取最新 Skill 代码..."

git fetch origin main
LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
    echo "✅ 本地 stock-prompt 技能库已经是最新版！"
else
    git pull origin main
    if [ -f "$REPO_DIR/version.json" ]; then
        NEW_VER=$(grep -o '"latest": "[^"]*"' "$REPO_DIR/version.json" | cut -d'"' -f4)
        echo "🎉 成功更新至最新版本: v${NEW_VER}"
    else
        echo "🎉 成功更新至最新版本！"
    fi
fi
