#!/usr/bin/env python3
"""Tests the runner against the stub CLI: python conformance/runner/test_runner.py"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def run(mode, suite="*", by=None):
    with tempfile.TemporaryDirectory() as d:
        cmd = [sys.executable, str(HERE / "stub_cli.py"), "--mode", mode] + (["--by", str(by)] if by else [])
        cfg = Path(d) / "impl.json"
        cfg.write_text(json.dumps({"stub": {"command": cmd}}))
        p = subprocess.run([sys.executable, str(HERE / "runner.py"), "--impl", "stub", "--config", str(cfg), "--report", d, "--suite", suite],
                           capture_output=True, text=True)
        rep = Path(d) / "stub.json"
        return p.returncode, json.loads(rep.read_text()) if rep.exists() else None, p.stdout + p.stderr


class StubTests(unittest.TestCase):
    def test_replay_passes_every_case(self):
        code, rep, out = run("replay")
        self.assertEqual(code, 0, out)
        t = rep["totals"]
        self.assertEqual(t["pass"], t["cases"])
        self.assertGreater(t["cases"], 3000)

    def test_small_noise_inside_tolerance_passes(self):
        code, rep, out = run("perturb", "compounding", 1e-13)
        self.assertEqual(rep["totals"]["fail"], 0, out)

    def test_lone_surrogate_reaches_the_cli(self):
        code, rep, out = run("replay", "store_a4")
        self.assertEqual(code, 0, out)

    def test_noise_outside_tolerance_fails(self):
        code, rep, _ = run("perturb", "compounding", 1e-6)
        self.assertEqual(code, 1)
        self.assertGreater(rep["totals"]["fail"], 800)

    def test_exact_class_rejects_tiny_noise(self):
        code, rep, _ = run("perturb", "sobol", 1e-15)
        self.assertEqual(code, 1)

    def test_wrong_error_code_fails(self):
        code, rep, _ = run("wrong_error", "daycount")
        self.assertEqual(rep["totals"]["fail"], 6)

    def test_missing_and_extra_keys_fail(self):
        for m in ("drop_key", "extra_key"):
            code, rep, _ = run(m, "compounding")
            self.assertEqual(code, 1)

    def test_unsupported_is_not_a_pass(self):
        code, rep, _ = run("unsupported", "sobol")
        self.assertEqual(code, 1)
        self.assertEqual(rep["totals"]["pass"], 0)
        self.assertEqual(rep["totals"]["not_implemented"], rep["totals"]["cases"])

    def test_crash_and_short_output_are_caught(self):
        for m in ("crash", "short"):
            code, rep, _ = run(m, "sobol")
            self.assertEqual(code, 1)
            self.assertTrue(rep["suites"][0]["crash"])

    def test_nan_token_fails(self):
        code, rep, _ = run("nan", "compounding")
        self.assertEqual(code, 1)

    def test_contract_mismatch_stops(self):
        code, rep, _ = run("bad_contract", "sobol")
        self.assertEqual(code, 1)
        self.assertIsNone(rep)


class CommandTests(unittest.TestCase):
    def test_relative_path_gains_suffix_and_root(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "build").mkdir()
            (Path(d) / "build" / "quantforge.exe").write_text("")
            argv, cwd = runner.resolve_command({"command": ["build/quantforge", "x"], "cwd": "."}, d, windows=True)
            self.assertEqual(Path(argv[0]), (Path(d) / "build" / "quantforge.exe").resolve())
            self.assertEqual(argv[1], "x")
            self.assertEqual(Path(cwd), Path(d) / ".")

    def test_no_suffix_added_off_windows(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tool.exe").write_text("")
            argv, _ = runner.resolve_command({"command": ["./tool"]}, d, windows=False)
            self.assertEqual(argv[0], "./tool")

    def test_bare_name_uses_path(self):
        argv, _ = runner.resolve_command({"command": [Path(sys.executable).name]}, ROOT)
        self.assertTrue(Path(argv[0]).is_absolute())

    @unittest.skipUnless(sys.platform == "win32", "needs a Windows launcher")
    def test_end_to_end_relative_launcher_from_another_directory(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bin").mkdir()
            (Path(d) / "bin" / "qf.cmd").write_text(f'@"{sys.executable}" "{HERE / "stub_cli.py"}" %*\r\n')
            cfg = Path(d) / "impl.json"
            cfg.write_text(json.dumps({"stub": {"command": ["bin/qf"], "cwd": d}}))
            p = subprocess.run([sys.executable, str(HERE / "runner.py"), "--impl", "stub", "--config", str(cfg), "--report", d, "--suite", "sobol"],
                               capture_output=True, text=True, cwd=tempfile.gettempdir())
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class CompareTests(unittest.TestCase):
    cls = {"absolute": 1e-12, "relative": 1e-10}

    def test_null_only_equals_null(self):
        self.assertTrue(runner.compare(0.0, None, self.cls, None, "x"))
        self.assertFalse(runner.compare(None, None, self.cls, None, "x"))

    def test_bool_is_not_number(self):
        self.assertTrue(runner.compare(1, True, {"exact": True}, None, "x"))
        self.assertTrue(runner.compare(True, 1.0, {"exact": True}, None, "x"))

    def test_negative_zero_equals_zero(self):
        self.assertFalse(runner.compare(-0.0, 0.0, {"exact": True}, None, "x"))

    def test_limit_override(self):
        self.assertFalse(runner.compare(1.1, 1.0, self.cls, {"absolute": 0.2}, "x"))

    def test_confidence_interval(self):
        chk = {"output": "p", "expected": 1.0, "method": "confidence_interval", "stderr_output": "s", "z": 4.0}
        self.assertFalse(runner.extra_check(chk, {"p": 1.3, "s": 0.1}))
        self.assertTrue(runner.extra_check(chk, {"p": 1.5, "s": 0.1}))

    def test_policy_has_every_class_used(self):
        classes = runner.load_policy(ROOT / "conformance/tolerances/policy.yaml")
        self.assertEqual(classes["simple_analytic"]["absolute"], 1e-12)
        self.assertTrue(classes["bit_exact"]["exact"])
        for p in (ROOT / "datasets/golden").rglob("*.json"):
            for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
                self.assertIn(c["tolerance_class"], classes)


if __name__ == "__main__":
    unittest.main(verbosity=1)
