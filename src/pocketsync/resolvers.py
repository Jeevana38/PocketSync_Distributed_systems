from __future__ import annotations

from datetime import date
from typing import Any

from pocketsync.models import Mutation, Record


STATUS_ORDER = {
    "saved": 0,
    "applied": 1,
    "phone_screen": 2,
    "interview": 3,
    "offer": 4,
    "rejected": 5,
}

IMMUTABLE_FIELDS = {"company", "role", "location"}
APPEND_FIELDS = {"notes"}


def empty_meta() -> dict[str, Any]:
    return {"record_ts": -1, "field_ts": {}, "field_writer": {}}


def resolve(policy: str, current: Record | None, meta: dict[str, Any] | None, mutation: Mutation) -> tuple[Record, dict[str, Any]]:
    current = dict(current or {})
    meta = dict(meta or empty_meta())
    meta.setdefault("field_ts", {})
    meta.setdefault("field_writer", {})

    if policy == "record_lww":
        return record_lww(current, meta, mutation)
    if policy == "field_lww":
        return field_lww(current, meta, mutation)
    if policy == "schema_aware":
        return schema_aware(current, meta, mutation)
    raise ValueError(f"unknown conflict policy: {policy}")


def record_lww(current: Record, meta: dict[str, Any], mutation: Mutation) -> tuple[Record, dict[str, Any]]:
    if _newer(mutation, meta.get("record_ts", -1), meta.get("record_writer", "")):
        next_record = dict(mutation.patch)
        next_record["record_id"] = mutation.record_id
        return next_record, {"record_ts": mutation.timestamp, "record_writer": mutation.op_id, "field_ts": {}, "field_writer": {}}
    return current, meta


def field_lww(current: Record, meta: dict[str, Any], mutation: Mutation) -> tuple[Record, dict[str, Any]]:
    for field, value in mutation.patch.items():
        if field == "record_id":
            continue
        field_ts = meta["field_ts"].get(field, -1)
        field_writer = meta["field_writer"].get(field, "")
        if _newer(mutation, field_ts, field_writer):
            current[field] = value
            meta["field_ts"][field] = mutation.timestamp
            meta["field_writer"][field] = mutation.op_id
    meta["record_ts"] = max(meta.get("record_ts", -1), mutation.timestamp)
    return current, meta


def schema_aware(current: Record, meta: dict[str, Any], mutation: Mutation) -> tuple[Record, dict[str, Any]]:
    for field, value in mutation.patch.items():
        if field == "record_id":
            continue
        if field in IMMUTABLE_FIELDS and current.get(field) not in (None, ""):
            _touch(meta, field, mutation)
            continue
        if field in APPEND_FIELDS:
            current[field] = _merge_notes(current.get(field, ""), value)
            _touch(meta, field, mutation)
            continue
        if field == "status":
            current[field] = _max_status(current.get(field), str(value))
            _touch(meta, field, mutation)
            continue
        if field in {"last_contacted", "next_deadline"}:
            current[field] = _max_date(current.get(field), value)
            _touch(meta, field, mutation)
            continue

        field_ts = meta["field_ts"].get(field, -1)
        field_writer = meta["field_writer"].get(field, "")
        if _newer(mutation, field_ts, field_writer):
            current[field] = value
            _touch(meta, field, mutation)
    meta["record_ts"] = max(meta.get("record_ts", -1), mutation.timestamp)
    return current, meta


def _newer(mutation: Mutation, old_ts: int, old_writer: str) -> bool:
    return (mutation.timestamp, mutation.op_id) >= (old_ts, old_writer)


def _touch(meta: dict[str, Any], field: str, mutation: Mutation) -> None:
    meta["field_ts"][field] = max(meta["field_ts"].get(field, -1), mutation.timestamp)
    meta["field_writer"][field] = mutation.op_id


def _merge_notes(existing: Any, incoming: Any) -> str:
    lines: set[str] = set()
    for value in (existing, incoming):
        for line in str(value or "").splitlines():
            clean = line.strip()
            if clean:
                lines.add(clean)
    return "\n".join(sorted(lines))


def _max_status(left: Any, right: str) -> str:
    left = str(left or "saved")
    return right if STATUS_ORDER.get(right, -1) >= STATUS_ORDER.get(left, -1) else left


def _max_date(left: Any, right: Any) -> Any:
    if not left:
        return right
    if not right:
        return left
    try:
        return max(date.fromisoformat(str(left)), date.fromisoformat(str(right))).isoformat()
    except ValueError:
        return right
