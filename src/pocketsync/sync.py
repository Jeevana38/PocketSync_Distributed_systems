from __future__ import annotations

from dataclasses import dataclass
import json

from pocketsync.store import ReplicaStore


@dataclass(frozen=True)
class SyncResult:
    left_sent: int
    right_sent: int
    left_applied: int
    right_applied: int
    bytes_transferred: int

    @property
    def total_messages(self) -> int:
        return self.left_sent + self.right_sent


def sync_pair(left: ReplicaStore, right: ReplicaStore) -> SyncResult:
    """Run one pairwise anti-entropy round between two replicas."""
    left_summary = left.summary()
    right_summary = right.summary()

    left_missing_at_right = left.missing_since(right_summary)
    right_missing_at_left = right.missing_since(left_summary)
    bytes_transferred = _payload_size(left_missing_at_right) + _payload_size(right_missing_at_left)

    right_applied = right.apply_many(left_missing_at_right)
    left_applied = left.apply_many(right_missing_at_left)

    return SyncResult(
        left_sent=len(left_missing_at_right),
        right_sent=len(right_missing_at_left),
        left_applied=left_applied,
        right_applied=right_applied,
        bytes_transferred=bytes_transferred,
    )


def _payload_size(mutations: list) -> int:
    payload = [mutation.to_dict() for mutation in mutations]
    return len(json.dumps(payload, sort_keys=True).encode("utf-8"))
