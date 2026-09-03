#!/usr/bin/env bash

# =================================================================
# stock-prompt Skill 一键更新脚本 (Linux / macOS)
# 拉取最新代码 -> 同步全局技能副本 -> 防漂移校验
# =================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "🔍 正在检查本地版本与远程 repository 状态..."

if [ -n "$(git status --porcelain)" ]; then
    echo "❌ 检测到尚未提交的本地修改。为避免覆盖你的自定义内容，本次更新已停止。"
    echo "   请先提交、暂存或备份这些修改，再重新运行更新脚本。"
    exit 1
fi

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
    git pull --ff-only origin main
    if [ -f "$REPO_DIR/version.json" ]; then
        NEW_VER=$(grep -o '"latest": "[^"]*"' "$REPO_DIR/version.json" | cut -d'"' -f4)
        echo "🎉 成功更新至最新版本: v${NEW_VER}"
    else
        echo "🎉 成功更新至最新版本！"
    fi
fi

echo ""
echo "🛠 正在同步技能到本机全局环境 (Gemini / Antigravity / Codex)..."
PY_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PY_BIN=python3
elif command -v python >/dev/null 2>&1; then
    PY_BIN=python
fi
if [ -n "$PY_BIN" ]; then
    if "$PY_BIN" scripts/install_skills.py && "$PY_BIN" scripts/install_skills.py --check; then
        echo "✅ 全局技能副本已同步并通过一致性校验。"
    else
        echo "[WARN] 全局同步未完全成功，可稍后手动运行: python3 scripts/install_skills.py"
    fi
else
    echo "[WARN] 未检测到 python3 或 python，跳过全局同步（仓库内技能已是最新）。"
fi
