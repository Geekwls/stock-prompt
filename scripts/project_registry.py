#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock-prompt 项目注册表统一接入层 (Project Registry Access Layer)
负责加载、校验 registry.json，统一提供 Skill、Prompt、契约、脚本与 MCP 服务配置，
消除各同步脚本与测试中的硬编码，防止死链与配置漂移。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "registry.json"


class RegistryError(Exception):
    """注册表校验异常"""
    pass


def resolve_path(relative_or_path: Union[str, Path], root: Path = ROOT) -> Path:
    """将相对路径解析为相对于项目根目录的绝对路径。"""
    path = Path(relative_or_path)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def load_registry(registry_file: Path = REGISTRY_PATH) -> Dict[str, Any]:
    """加载并校验 registry.json 文件。"""
    registry_file = Path(registry_file)
    if not registry_file.is_file():
        raise RegistryError(f"注册表文件不存在: {registry_file}")
    try:
        with registry_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"注册表 JSON 格式解析失败: {exc}") from exc
    validate_registry(data, root=registry_file.parent)
    return data


def validate_registry(data: Dict[str, Any], root: Path = ROOT) -> None:
    """对注册表进行结构完整性与路径死链校验。"""
    if not isinstance(data, dict):
        raise RegistryError("注册表根节点必须为 JSON 对象")

    for field in ("project", "skills", "schemas", "mcp", "contracts", "script_sources"):
        if field not in data:
            raise RegistryError(f"注册表缺失必填字段: {field}")

    project = data.get("project")
    if not isinstance(project, dict) or not project.get("version"):
        raise RegistryError("project.version 必须是非空字符串")

    skills = data.get("skills")
    if not isinstance(skills, list) or not skills:
        raise RegistryError("skills 必须是非空列表")

    skill_ids = set()
    for index, skill in enumerate(skills):
        if not isinstance(skill, dict):
            raise RegistryError(f"skills[{index}] 必须为对象")
        for k in ("id", "display_name", "source", "prompt_target", "bundled_scripts"):
            if k not in skill:
                raise RegistryError(f"Skill 项缺失字段 {k}: {skill}")

        s_id = skill["id"]
        if s_id in skill_ids:
            raise RegistryError(f"存在重复的 Skill ID: {s_id}")
        skill_ids.add(s_id)

        source_dir = resolve_path(skill["source"], root=root)
        if not source_dir.is_dir():
            raise RegistryError(f"Skill source 目录不存在: {source_dir} (id: {s_id})")
        skill_md = source_dir / "SKILL.md"
        if not skill_md.is_file():
            raise RegistryError(f"Skill 缺失 SKILL.md: {skill_md}")

    # 校验 schemas 路径
    schemas = data.get("schemas", {})
    for s_name, s_rel in schemas.items():
        s_path = resolve_path(s_rel, root=root)
        if not s_path.is_file():
            raise RegistryError(f"Schema 文件不存在: {s_path} (key: {s_name})")

    # 校验 contracts
    contracts = data.get("contracts", {})
    c_source = resolve_path(contracts.get("common_source", ""), root=root)
    if not c_source.is_file():
        raise RegistryError(f"公共契约源文件不存在: {c_source}")

    # 校验 mcp
    mcp = data.get("mcp", {})
    mcp_server = resolve_path(mcp.get("entrypoint", ""), root=root)
    if not mcp_server.is_file():
        raise RegistryError(f"MCP 服务端入口不存在: {mcp_server}")
    tools = mcp.get("tools", [])
    if len(tools) != 12:
        raise RegistryError(f"MCP tools 数量期望 12，实际为 {len(tools)}")

    # 校验 script_sources 母本是否存在
    script_sources = data.get("script_sources", {})
    for name, relative in script_sources.items():
        s_file = resolve_path(relative, root=root)
        if not s_file.is_file():
            raise RegistryError(f"公共脚本母本不存在: {s_file} (name: {name})")


def get_project_version(registry_file: Path = REGISTRY_PATH) -> str:
    data = load_registry(registry_file)
    return str(data["project"]["version"])


def get_skill_names(registry_file: Path = REGISTRY_PATH) -> Tuple[str, ...]:
    data = load_registry(registry_file)
    return tuple(s["id"] for s in data["skills"])


def get_skills(registry_file: Path = REGISTRY_PATH) -> List[Dict[str, Any]]:
    data = load_registry(registry_file)
    return list(data["skills"])


def get_bundled_scripts_mapping(registry_file: Path = REGISTRY_PATH, root: Path = ROOT) -> Dict[str, Tuple[Path, Tuple[str, ...]]]:
    data = load_registry(registry_file)
    return {
        name: (
            resolve_path(relative, root=root),
            tuple(item["id"] for item in data["skills"] if name in item.get("bundled_scripts", [])),
        )
        for name, relative in data["script_sources"].items()
    }


def get_prompt_sync_mappings(registry_file: Path = REGISTRY_PATH, root: Path = ROOT) -> Dict[Path, Path]:
    data = load_registry(registry_file)
    return {
        resolve_path(item["source"], root=root) / "SKILL.md": resolve_path(item["prompt_target"], root=root)
        for item in data["skills"]
    }


def get_contract_sync_mappings(registry_file: Path = REGISTRY_PATH, root: Path = ROOT) -> Tuple[Path, Tuple[Path, ...]]:
    data = load_registry(registry_file)
    source = resolve_path(data["contracts"]["common_source"], root=root)
    targets = tuple(
        resolve_path(item["source"], root=root) / data["contracts"]["target_name"]
        for item in data["skills"]
    )
    return source, targets


def get_mcp_config(registry_file: Path = REGISTRY_PATH) -> Dict[str, Any]:
    data = load_registry(registry_file)
    return data["mcp"]


if __name__ == "__main__":
    reg = load_registry()
    print(f"[OK] 注册表有效: 项目 {reg['project']['name']} v{reg['project']['version']}, 包含 {len(reg['skills'])} 个技能")
