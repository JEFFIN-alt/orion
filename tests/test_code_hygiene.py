"""Execution module scope and import-warning hygiene checks."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from orion.execution import ExecutionService


class CodeHygieneTests(unittest.TestCase):
    def test_execute_has_no_shadowed_research_names(self):
        names=ExecutionService.execute.__code__.co_varnames
        self.assertNotIn('digest',names)
        self.assertNotIn('canonical',names)

    def test_execution_imports_with_warnings_as_errors(self):
        root=Path(__file__).resolve().parents[1]
        env=dict(os.environ,PYTHONPATH=str(root/'src'))
        result=subprocess.run([sys.executable,'-W','error','-c','import orion.execution'],cwd=root,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
