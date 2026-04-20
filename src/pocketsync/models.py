from __future__ import annotations

from dataclasses import dataclass
from typing import Any


Record = dict[str, Any]
Summary = dict[str, int]


@dataclass(frozen=True)
class Mutation:
    replica_id: str
    counter: int
    record_id: str
    patch: Record
    timestamp: int

    @property
    def op_id(self) -> str:
        return f"{self.replica_id}:{self.counter}"

    def to_row(self) -> tuple[str, str, int, str, Record, int]:
        return (self.op_id, self.replica_id, self.counter, self.record_id, self.patch, self.timestamp)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mutation":
        return cls(
            replica_id=data["replica_id"],
            counter=int(data["counter"]),
            record_id=data["record_id"],
            patch=dict(data["patch"]),
            timestamp=int(data["timestamp"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_id": self.op_id,
            "replica_id": self.replica_id,
            "counter": self.counter,
            "record_id": self.record_id,
            "patch": self.patch,
            "timestamp": self.timestamp,
        }


def dominates(summary: Summary, mutation: Mutation) -> bool:
    return summary.get(mutation.replica_id, 0) >= mutation.counter


def advance(summary: Summary, mutation: Mutation) -> Summary:
    updated = dict(summary)
    updated[mutation.replica_id] = max(updated.get(mutation.replica_id, 0), mutation.counter)
    return updated
