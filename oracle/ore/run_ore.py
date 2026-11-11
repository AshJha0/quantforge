"""Run one ORE case directory (ORE 1.8.17.0, Python wheel, under WSL): python run_ore.py <case dir>."""
import os
import sys

import ORE

os.chdir(sys.argv[1])
os.makedirs("Output", exist_ok=True)
import re
out = re.search(r'name="outputPath">([^<]*)<', open("ore.xml").read()).group(1)
os.makedirs(out, exist_ok=True)
params = ORE.Parameters()
params.fromFile("ore.xml")
app = ORE.OREApp(params)
app.run()
print("errors:", list(app.getErrors()))
if out != "Output":  # outputs written on the Linux file system (fast), the net cube copied back
    import shutil
    for f in ("netcube.csv", "npv.csv", "log.txt"):
        if os.path.exists(os.path.join(out, f)):
            shutil.copy(os.path.join(out, f), os.path.join("Output", f))
