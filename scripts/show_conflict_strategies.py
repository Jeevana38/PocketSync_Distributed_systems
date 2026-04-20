#!/usr/bin/env python3
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pocketsync.experiment import POLICIES, run_policy


def main() -> None:
    root = ROOT / "demo_conflicts"
    root.mkdir(exist_ok=True)
    for db in root.glob("**/*.db"):
        db.unlink()

    for policy in POLICIES:
        result = run_policy(policy, root / policy)
        print("=" * 72)
        print(f"Policy: {policy}")
        print(
            "Metrics: "
            f"converged={result['converged']}, "
            f"rounds={result['anti_entropy_rounds']}, "
            f"mutations={result['mutations_transferred']}, "
            f"bytes={result['bytes_transferred']}, "
            f"preserved_fields={result['preserved_structured_fields']}/{result['expected_structured_fields']}, "
            f"lost_fields={result['lost_structured_fields']}, "
            f"note_lines={result['note_lines']}"
        )
        print("Final merged record:")
        print(json.dumps(result["final_record"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
