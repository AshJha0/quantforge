#!/usr/bin/env python3
"""Tests for tools/check_cookbook.py: python tools/test_check_cookbook.py (standard library; needs bash)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_cookbook", ROOT / "tools/check_cookbook.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

PAGE = """# Page

#### First recipe

<!-- cookbook:run -->
```bash
echo '{"a":1,"b":2}'
```
<!-- cookbook:expect
"a":1
"b":2
-->

#### Unmarked recipe

```bash
exit 1
```
"""


class Parse(unittest.TestCase):
    def test_pairs_run_and_expect_under_their_heading(self):
        items = cc.recipes(PAGE)
        self.assertEqual(len(items), 1)
        title, body, want = items[0]
        self.assertEqual(title, "First recipe")
        self.assertIn("echo", body)
        self.assertEqual(want, ['"a":1', '"b":2'])

    def test_run_without_expect_is_an_error(self):
        with self.assertRaises(ValueError):
            cc.recipes(PAGE.replace("<!-- cookbook:expect\n\"a\":1\n\"b\":2\n-->\n", ""))

    def test_expect_without_run_is_an_error(self):
        with self.assertRaises(ValueError):
            cc.recipes(PAGE.replace("<!-- cookbook:run -->\n", ""))

    def test_empty_expect_is_an_error(self):
        with self.assertRaises(ValueError):
            cc.recipes(PAGE.replace("\"a\":1\n\"b\":2\n", ""))


class Run(unittest.TestCase):
    def _file(self, text):
        d = tempfile.mkdtemp()
        f = Path(d) / "COOKBOOK.md"
        f.write_text(text, encoding="utf-8")
        return str(f)

    def test_matching_page_passes(self):
        self.assertEqual(cc.main(["--file", self._file(PAGE)]), 0)

    def test_planted_wrong_number_fails(self):
        self.assertEqual(cc.main(["--file", self._file(PAGE.replace('"b":2\n-->', '"b":3\n-->'))]), 1)

    def test_failing_command_fails(self):
        self.assertEqual(cc.main(["--file", self._file(PAGE.replace("echo '", "false; echo '"))]), 1)

    def test_uv_shim_swaps_the_launcher_for_the_module(self):
        self.assertIn("python -m quantforge_core.cli.main", cc.shims())

    def test_real_cookbook_markers_parse(self):
        self.assertGreaterEqual(len(cc.recipes((ROOT / "COOKBOOK.md").read_text(encoding="utf-8"))), 16)


if __name__ == "__main__":
    unittest.main()
