#!/bin/zsh
# Excel parity test: fills the house template with test portfolios, calculates it with real Excel formulas
# (the `formulas` engine) and with the website's allocation engine, and compares every summary/table cell.
#   ./run.sh "/path/to/אלוקציה פרימיום.xlsx"
# Needs: python with openpyxl + formulas (pip install formulas), node.
set -e
WB="$1"; cd "$(dirname "$0")"; mkdir -p out; cp *.py out/; cd out
PY=${PYTHON:-python3}
for c in "2 0.3" "3 0.5" "4 0.75" "5 0.2"; do s=${c% *}; e=${c#* }
  NO96=1 $PY build.py "$WB" $s $e >/dev/null && $PY -W ignore calc.py case$s.xlsx xl$s.json >/dev/null 2>&1
  node ../site.mjs case$s.json site$s.json >/dev/null; echo "== ישראל + חו״ל, $e מניות"; $PY compare.py xl$s.json site$s.json res$s.json; done
for c in "11 0.3" "12 0.5"; do s=${c% *}; e=${c#* }
  $PY build_il.py "$WB" $s $e && $PY -W ignore calc.py il$s.xlsx xil$s.json >/dev/null 2>&1
  node ../site.mjs il$s.json sil$s.json >/dev/null; echo "== ישראל בלבד, $e מניות"; $PY compare_il.py xil$s.json sil$s.json ril$s.json; done
# Export check (needs the backend on :8000): the "אקסל" export of saved models 8 and 9, calculated as exported and
# with the equity share changed inside Excel, must equal the website.
mkdir -p exp && node ../export_check.mjs 8 30 exp && $PY -W ignore ../export_compare.py exp
mkdir -p exp9 && node ../export_check.mjs 9 45 exp9 && $PY -W ignore ../export_compare.py exp9
