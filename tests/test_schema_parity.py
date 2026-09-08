import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "check_schema_parity.py"
SPEC = importlib.util.spec_from_file_location("check_schema_parity", MODULE)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class SchemaParityTest(unittest.TestCase):
    def test_schema_runtime_and_examples_are_aligned(self):
        self.assertEqual(CHECKER.collect_errors(), [])
