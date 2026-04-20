#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import statistics
import tempfile
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pocketsync.experiment import POLICIES
from pocketsync.store import ReplicaStore
from pocketsync.sync import sync_pair


REPLICA_IDS = ("laptop", "phone", "tablet")
STATUSES = ("saved", "applied", "phone_screen", "interview", "offer", "rejected")
FIELDS = ("status", "next_deadline", "last_contacted", "notes")


def seed_record(index: int) -> dict[str, str]:
    return {
        "company": f"Company {index}",
        "role": "Software Engineer",
        "location": "Remote",
        "status": "saved",
        "next_deadline": "2026-04-15",
        "last_contacted": "2026-04-01",
        "notes": f"Seed note for job-{index}.",
    }


def random_patch(rng: random.Random, op_index: int) -> tuple[dict[str, str], dict[str, str]]:
    field = rng.choice(FIELDS)
    if field == "status":
        value = rng.choice(STATUSES)
    elif field == "next_deadline":
        value = f"2026-04-{rng.randint(16, 28):02d}"
    elif field == "last_contacted":
        value = f"2026-04-{rng.randint(2, 20):02d}"
    else:
        value = f"Offline note {op_index}"
    return {field: value}, {field: value}


def run_trial(policy: str, root: Path, records: int, offline_ops: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    replicas = {
        replica_id: ReplicaStore(root / f"{replica_id}.db", replica_id=replica_id, policy=policy)
        for replica_id in REPLICA_IDS
    }
    expected_by_record: dict[str, dict[str, str]] = {}
    try:
        for index in range(1, records + 1):
            record_id = f"job-{index}"
            replicas["laptop"].local_update(record_id, seed_record(index))
            expected_by_record[record_id] = {}

        sync_pair(replicas["laptop"], replicas["phone"])
        sync_pair(replicas["laptop"], replicas["tablet"])

        for op_index in range(1, offline_ops + 1):
            replica_id = rng.choice(REPLICA_IDS)
            record_id = f"job-{rng.randint(1, records)}"
            patch, expected = random_patch(rng, op_index)
            replicas[replica_id].local_update(record_id, patch)
            expected_by_record[record_id].update(expected)

        rounds = [
            sync_pair(replicas["laptop"], replicas["phone"]),
            sync_pair(replicas["phone"], replicas["tablet"]),
            sync_pair(replicas["laptop"], replicas["tablet"]),
        ]

        states = {replica_id: replicas[replica_id].records() for replica_id in REPLICA_IDS}
        converged = len({str(state) for state in states.values()}) == 1
        final_records = states["laptop"]

        expected_fields = 0
        preserved_fields = 0
        for record_id, fields in expected_by_record.items():
            final = final_records.get(record_id, {})
            for field, value in fields.items():
                expected_fields += 1
                if field == "notes":
                    if value in str(final.get("notes", "")):
                        preserved_fields += 1
                elif final.get(field) == value:
                    preserved_fields += 1

        return {
            "policy": policy,
            "converged": converged,
            "rounds": len(rounds),
            "mutations_transferred": sum(result.total_messages for result in rounds),
            "bytes_transferred": sum(result.bytes_transferred for result in rounds),
            "expected_fields": expected_fields,
            "preserved_fields": preserved_fields,
            "lost_fields": expected_fields - preserved_fields,
        }
    finally:
        for replica in replicas.values():
            replica.close()


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy: dict[str, list[dict[str, Any]]] = {policy: [] for policy in POLICIES}
    for row in rows:
        by_policy[row["policy"]].append(row)

    summaries = []
    for policy, policy_rows in by_policy.items():
        preserved_rates = [
            row["preserved_fields"] / row["expected_fields"] if row["expected_fields"] else 1.0
            for row in policy_rows
        ]
        summaries.append(
            {
                "policy": policy,
                "trials": len(policy_rows),
                "convergence_rate": sum(1 for row in policy_rows if row["converged"]) / len(policy_rows),
                "avg_mutations": statistics.mean(row["mutations_transferred"] for row in policy_rows),
                "avg_bytes": statistics.mean(row["bytes_transferred"] for row in policy_rows),
                "avg_preserved_rate": statistics.mean(preserved_rates),
                "avg_lost_fields": statistics.mean(row["lost_fields"] for row in policy_rows),
            }
        )
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Run randomized PocketSync evaluation.")
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--records", type=int, default=10)
    parser.add_argument("--offline-ops", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rows = []
    with tempfile.TemporaryDirectory(prefix="pocketsync-random-") as tmp:
        root = Path(tmp)
        for trial in range(args.trials):
            for policy in POLICIES:
                rows.append(
                    run_trial(
                        policy=policy,
                        root=root / f"{policy}-{trial}",
                        records=args.records,
                        offline_ops=args.offline_ops,
                        seed=args.seed + trial,
                    )
                )

    print("policy,trials,convergence_rate,avg_mutations,avg_bytes,avg_preserved_rate,avg_lost_fields")
    for row in summarize(rows):
        print(
            f"{row['policy']},{row['trials']},{row['convergence_rate']:.2f},"
            f"{row['avg_mutations']:.2f},{row['avg_bytes']:.2f},"
            f"{row['avg_preserved_rate']:.2f},{row['avg_lost_fields']:.2f}"
        )


if __name__ == "__main__":
    main()
