"""Calculate a test workbook with the `formulas` engine and dump the cells we compare."""
import json, sys
from pathlib import Path
import formulas

xl = Path(sys.argv[1]).resolve()
model = formulas.ExcelModel().loads(str(xl)).finish()
sol = model.calculate()
vals = {}
for k, v in sol.items():
    ref = k.split("!")[-1].upper()
    if ":" in ref:
        continue
    try:
        x = v.value[0][0]
    except Exception:
        continue
    try:
        vals[ref] = float(x)
    except Exception:
        vals[ref] = str(x)
Path(sys.argv[2]).write_text(json.dumps(vals, ensure_ascii=False))
print(len(vals), "cells")
