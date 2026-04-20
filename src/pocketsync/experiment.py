from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from pocketsync.store import ReplicaStore
from pocketsync.sync import sync_pair


POLICIES = ("record_lww", "field_lww", "schema_aware")


def run_policy(policy: str, root: Path) -> dict[str, Any]:
    replicas = {
        name: ReplicaStore(root / f"{name}.db", replica_id=name, policy=policy)
        for name in ("laptop", "phone", "tablet")
    }
    try:
        seed = {
            "company": "Acme Robotics",
            "role": "Distributed Systems Engineer",
            "location": "Boulder",
            "status": "saved",
            "next_deadline": "2026-04-15",
            "last_contacted": "2026-04-01",
            "notes": "Found posting on LinkedIn.",
        }
        replicas["laptop"].local_update("job-1", seed)
        sync_pair(replicas["laptop"], replicas["phone"])
        sync_pair(replicas["laptop"], replicas["tablet"])

        # Offline partition: each device accepts local edits independently.
        replicas["laptop"].local_update("job-1", {"status": "interview", "notes": "Recruiter asked for availability."})
        replicas["phone"].local_update("job-1", {"next_deadline": "2026-04-20", "notes": "Added reminder from phone."})
        replicas["tablet"].local_update("job-1", {"last_contacted": "2026-04-10", "notes": "Prepared system design notes."})

        rounds = [
            sync_pair(replicas["laptop"], replicas["phone"]),
            sync_pair(replicas["phone"], replicas["tablet"]),
            sync_pair(replicas["laptop"], replicas["tablet"]),
        ]
        states = {name: store.get_record("job-1") for name, store in replicas.items()}
        converged = len({str(state) for state in states.values()}) == 1
        final = states["laptop"] or {}
        expected = {
            "status": "interview",
            "next_deadline": "2026-04-20",
            "last_contacted": "2026-04-10",
        }
        preserved_fields = sum(final.get(field) == value for field, value in expected.items())
        note_lines = len(str(final.get("notes", "")).splitlines())
        total_bytes = sum(result.bytes_transferred for result in rounds)
        lost_fields = len(expected) - preserved_fields

        return {
            "policy": policy,
            "converged": converged,
            "anti_entropy_rounds": len(rounds),
            "mutations_transferred": sum(result.total_messages for result in rounds),
            "bytes_transferred": total_bytes,
            "preserved_structured_fields": preserved_fields,
            "expected_structured_fields": len(expected),
            "lost_structured_fields": lost_fields,
            "note_lines": note_lines,
            "final_record": final,
        }
    finally:
        for replica in replicas.values():
            replica.close()


def run_all() -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="pocketsync-") as tmp:
        root = Path(tmp)
        return [run_policy(policy, root / policy) for policy in POLICIES]


def format_results(results: list[dict[str, Any]]) -> str:
    lines = [
        "policy,converged,rounds,mutations_transferred,bytes_transferred,preserved_fields,expected_fields,lost_fields,note_lines",
    ]
    for row in results:
        lines.append(
            "{policy},{converged},{anti_entropy_rounds},{mutations_transferred},{bytes_transferred},{preserved_structured_fields},{expected_structured_fields},{lost_structured_fields},{note_lines}".format(
                **row
            )
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_results(run_all()))
