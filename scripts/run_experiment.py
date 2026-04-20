#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pocketsync.experiment import format_results, run_all


if __name__ == "__main__":
    print(format_results(run_all()))
