"""Checks for the price reader, the forecast job and the monthly job, without network access.

    python3 -m unittest discover -s Tests -t .   # from the repo root
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The NECC page the app's tests read too.
FIXTURES = ROOT / "EggPaisaTests"

for folder in ("Analysis", "Pipeline", "Scripts"):
    if str(ROOT / folder) not in sys.path:
        sys.path.insert(0, str(ROOT / folder))
