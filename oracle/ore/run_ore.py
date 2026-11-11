"""Run one ORE case directory (ORE 1.8.17.0, Python wheel, under WSL): python run_ore.py <case dir>."""
import os
import sys

import ORE

os.chdir(sys.argv[1])
os.makedirs("Output", exist_ok=True)
params = ORE.Parameters()
params.fromFile("ore.xml")
app = ORE.OREApp(params)
app.run()
print("errors:", list(app.getErrors()))
