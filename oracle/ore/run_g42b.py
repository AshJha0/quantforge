"""Run the six G-42b ORE cases (oracle/ore/runb0..5, ruling G-42b), one at a time, in a Python 3.12 environment that has
the ORE 1.8.17.0 wheel (requirements-ore.txt). Each case is copied to a scratch directory with its output path set to
"Output", run there, and its net cube copied back to oracle/ore/runb<i>/Output/ (git-ignored).

    python run_g42b.py [--work DIR] [i ...]       # default: all six cases

Counting is a separate step: `uv run python -W ignore gen_stage_g_w4c.py countb` in oracle/python writes ORE_CHECK_4C_B.json (the
registered tolerances are in check_case_b; this script only runs ORE).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def one(i, work):
    src, dst = HERE / f"runb{i}", Path(work) / f"runb{i}"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("Output"))
    xml = (dst / "ore.xml").read_text()
    (dst / "ore.xml").write_text(re.sub(r'(name="outputPath">)[^<]*(<)', r"\1Output\2", xml))
    code = ("import os,sys,ORE; os.chdir(sys.argv[1]); os.makedirs('Output', exist_ok=True); p = ORE.Parameters(); p.fromFile('ore.xml'); "
            "a = ORE.OREApp(p); a.run(); e = list(a.getErrors()); print('errors:', e); sys.exit(1 if e else 0)")
    subprocess.run([sys.executable, "-I", "-c", code, str(dst)], check=True)
    out = HERE / f"runb{i}" / "Output"
    out.mkdir(exist_ok=True)
    for f in ("netcube.csv", "npv.csv", "log.txt"):
        if (dst / "Output" / f).exists():
            shutil.copy(dst / "Output" / f, out / f)
    print(f"runb{i}: netcube.csv {(out / 'netcube.csv').stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    work = tempfile.mkdtemp(prefix="g42b_")
    if a[:1] == ["--work"]:
        work, a = a[1], a[2:]
    for i in [int(x) for x in a] or range(6):
        one(i, work)
