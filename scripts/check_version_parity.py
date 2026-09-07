#!/usr/bin/env python3
"""校验项目、插件、MCP 组件、工具清单与发布标签的一致性。"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_registry import load_registry, resolve_path


ROOT = Path(__file__).resolve().parent.parent


def assigned_literal(path, variable):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"{path} 未找到 {variable}")


def collect_errors(tag=None):
    errors = []
    registry = load_registry()
    project_version = registry["project"]["version"]
    version = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))

    if version.get("latest") != project_version:
        errors.append(f"version.json={version.get('latest')} != registry={project_version}")
    if plugin.get("version") != project_version:
        errors.append(f"plugin.json={plugin.get('version')} != registry={project_version}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[v([^]]+)\]", changelog, re.MULTILINE)
    if not match or match.group(1) != project_version:
        errors.append("CHANGELOG 最新版本与 registry 不一致")

    expected_skills = [f"./{item['source']}" for item in registry["skills"]]
    if plugin.get("skills") != expected_skills:
        errors.append("plugin.json skills 与 registry 顺序或内容不一致")

    server_path = resolve_path(registry["mcp"]["entrypoint"])
    server_info = assigned_literal(server_path, "SERVER_INFO")
    schemas_path = server_path.parent / "marketgraph_mcp" / "schemas.py"
    tools_path = schemas_path if schemas_path.is_file() else server_path
    tools = assigned_literal(tools_path, "AVAILABLE_TOOLS")
    if server_info.get("name") != registry["mcp"]["name"]:
        errors.append("MCP 服务名与 registry 不一致")
    if server_info.get("version") != registry["mcp"]["version"]:
        errors.append("MCP 组件版本与 registry 不一致")
    actual_tools = [item.get("name") for item in tools]
    if actual_tools != registry["mcp"]["tools"]:
        errors.append("MCP 工具清单与 registry 顺序或内容不一致")

    if tag:
        normalized = tag[1:] if tag.startswith("v") else tag
        if normalized != project_version:
            errors.append(f"Git tag={tag} != v{project_version}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="校验 stock-prompt 版本与注册表一致性")
    parser.add_argument("--tag", help="可选发布标签，例如 v7.0.0")
    args = parser.parse_args()
    errors = collect_errors(args.tag)
    for error in errors:
        print(f"[FAIL] {error}")
    if errors:
        return 1
    print("[SUCCESS] 项目版本、组件版本、Skill 与 MCP 工具清单一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
