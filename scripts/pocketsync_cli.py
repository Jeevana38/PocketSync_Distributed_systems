#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pocketsync.store import ReplicaStore
from pocketsync.sync import sync_pair


DATA_DIR = ROOT / "demo_data"
DEFAULT_POLICY = "schema_aware"


def replica_path(replica_id: str) -> Path:
    return DATA_DIR / f"{replica_id}.db"


def open_replica(replica_id: str, policy: str) -> ReplicaStore:
    return ReplicaStore(replica_path(replica_id), replica_id=replica_id, policy=policy)


def parse_patch(values: list[str]) -> dict[str, str]:
    patch: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid field assignment {value!r}. Use field=value.")
        key, raw = value.split("=", 1)
        patch[key.strip()] = raw.strip()
    return patch


def cmd_reset(_: argparse.Namespace) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for db in DATA_DIR.glob("*.db"):
        db.unlink()
    print(f"Reset demo data in {DATA_DIR}")


def cmd_update(args: argparse.Namespace) -> None:
    store = open_replica(args.replica, args.policy)
    try:
        mutation = store.local_update(args.record, parse_patch(args.field))
        print(f"{args.replica} stored local offline update {mutation.op_id} for {args.record}")
    finally:
        store.close()


def cmd_show(args: argparse.Namespace) -> None:
    store = open_replica(args.replica, args.policy)
    try:
        if args.record:
            print(json.dumps(store.get_record(args.record), indent=2, sort_keys=True))
        else:
            print(json.dumps(store.records(), indent=2, sort_keys=True))
    finally:
        store.close()


def cmd_sync(args: argparse.Namespace) -> None:
    left = open_replica(args.left, args.policy)
    right = open_replica(args.right, args.policy)
    try:
        result = sync_pair(left, right)
        print(
            f"synced {args.left}<->{args.right}: "
            f"{args.left} sent {result.left_sent}, {args.right} sent {result.right_sent}, "
            f"applied {result.left_applied + result.right_applied} new mutations, "
            f"transferred about {result.bytes_transferred} bytes"
        )
    finally:
        left.close()
        right.close()


def cmd_summary(args: argparse.Namespace) -> None:
    store = open_replica(args.replica, args.policy)
    try:
        print(json.dumps(store.summary(), indent=2, sort_keys=True))
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual PocketSync demo CLI")
    parser.add_argument("--policy", default=DEFAULT_POLICY, choices=["record_lww", "field_lww", "schema_aware"])
    sub = parser.add_subparsers(required=True)

    reset = sub.add_parser("reset", help="delete local demo databases")
    reset.set_defaults(func=cmd_reset)

    update = sub.add_parser("update", help="apply an offline local update to one replica")
    update.add_argument("replica", help="replica id, for example laptop, phone, or tablet")
    update.add_argument("record", help="record id, for example job-1")
    update.add_argument("field", nargs="+", help="field=value assignments")
    update.set_defaults(func=cmd_update)

    show = sub.add_parser("show", help="show records stored on one replica")
    show.add_argument("replica")
    show.add_argument("record", nargs="?")
    show.set_defaults(func=cmd_show)

    sync = sub.add_parser("sync", help="run one pairwise anti-entropy sync")
    sync.add_argument("left")
    sync.add_argument("right")
    sync.set_defaults(func=cmd_sync)

    summary = sub.add_parser("summary", help="show the version summary for one replica")
    summary.add_argument("replica")
    summary.set_defaults(func=cmd_summary)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
