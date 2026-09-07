import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_version_parity.py"
SPEC = importlib.util.spec_from_file_location("check_version_parity", MODULE_PATH)
PARITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARITY)


def build_repo_snapshot(temporary):
    """复制真实项目文件到临时根，便于注入单点漂移。"""
    root = Path(temporary)
    (root / "scripts").mkdir()
    for source in ("version.json", "plugin.json", "registry.json", "CHANGELOG.md"):
        shutil.copy2(PARITY.ROOT / source, root / source)
    server_dir = root / "mcp" / "marketgraph-mcp"
    server_dir.mkdir(parents=True)
    shutil.copy2(PARITY.ROOT / "mcp" / "marketgraph-mcp" / "server.py", server_dir / "server.py")
    package_dir = server_dir / "marketgraph_mcp"
    package_dir.mkdir()
    shutil.copy2(
        PARITY.ROOT / "mcp" / "marketgraph-mcp" / "marketgraph_mcp" / "schemas.py",
        package_dir / "schemas.py",
    )
    return root


class VersionParityTest(unittest.TestCase):
    def setUp(self):
        self._original_root = PARITY.ROOT
        self._original_load_registry = PARITY.load_registry
        self._original_resolve_path = PARITY.resolve_path

    def tearDown(self):
        PARITY.ROOT = self._original_root
        PARITY.load_registry = self._original_load_registry
        PARITY.resolve_path = self._original_resolve_path

    def use_snapshot(self, root):
        """把 collect_errors 的数据源切到快照目录（函数级替换，规避默认参数绑定）。"""
        PARITY.ROOT = root
        PARITY.load_registry = lambda: json.loads((root / "registry.json").read_text(encoding="utf-8"))
        PARITY.resolve_path = lambda relative: (
            relative if Path(relative).is_absolute() else (root / relative).resolve()
        )

    def test_real_repo_has_no_drift(self):
        self.assertEqual(PARITY.collect_errors(), [])

    def test_tag_mismatch_is_reported(self):
        errors = PARITY.collect_errors(tag="v0.0.0")
        self.assertTrue(any("Git tag" in item for item in errors))

    def test_version_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_repo_snapshot(temporary)
            version = json.loads((root / "version.json").read_text(encoding="utf-8"))
            version["latest"] = "0.0.1"
            (root / "version.json").write_text(json.dumps(version, ensure_ascii=False), encoding="utf-8")
            self.use_snapshot(root)
            errors = PARITY.collect_errors()
            self.assertTrue(any("version.json" in item for item in errors))

    def test_changelog_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_repo_snapshot(temporary)
            changelog = root / "CHANGELOG.md"
            changelog.write_text("# CHANGELOG\n\n## [v0.0.1] - 2026-01-01\n", encoding="utf-8")
            self.use_snapshot(root)
            errors = PARITY.collect_errors()
            self.assertTrue(any("CHANGELOG" in item for item in errors))

    def test_plugin_skill_list_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_repo_snapshot(temporary)
            plugin = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
            plugin["skills"] = plugin["skills"][:1]
            (root / "plugin.json").write_text(json.dumps(plugin, ensure_ascii=False), encoding="utf-8")
            self.use_snapshot(root)
            errors = PARITY.collect_errors()
            self.assertTrue(any("plugin.json skills" in item for item in errors))

    def test_mcp_tool_list_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_repo_snapshot(temporary)
            schemas = root / "mcp" / "marketgraph-mcp" / "marketgraph_mcp" / "schemas.py"
            text = schemas.read_text(encoding="utf-8").replace('"get_stock_quote"', '"get_stock_quote_x"', 1)
            schemas.write_text(text, encoding="utf-8")
            self.use_snapshot(root)
            errors = PARITY.collect_errors()
            self.assertTrue(any("工具清单" in item for item in errors))

    def test_mcp_version_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_repo_snapshot(temporary)
            server = root / "mcp" / "marketgraph-mcp" / "server.py"
            text = server.read_text(encoding="utf-8").replace('"version": "1.7.0"', '"version": "9.9.9"', 1)
            server.write_text(text, encoding="utf-8")
            self.use_snapshot(root)
            errors = PARITY.collect_errors()
            self.assertTrue(any("MCP 组件版本" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
