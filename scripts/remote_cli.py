#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib import request


def parse_patch(values: list[str]) -> dict[str, str]:
    patch: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid field assignment {value!r}. Use field=value.")
        key, raw = value.split("=", 1)
        patch[key.strip()] = raw.strip()
    return patch


def http_get(base_url: str, path: str) -> object:
    with request.urlopen(base_url.rstrip("/") + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post(base_url: str, path: str, payload: object) -> object:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def cmd_update(args: argparse.Namespace) -> None:
    result = http_post(args.url, "/update", {"record_id": args.record, "patch": parse_patch(args.field)})
    print(json.dumps(result, indent=2, sort_keys=True))


def cmd_show(args: argparse.Namespace) -> None:
    path = f"/records/{args.record}" if args.record else "/records"
    print(json.dumps(http_get(args.url, path), indent=2, sort_keys=True))


def cmd_summary(args: argparse.Namespace) -> None:
    print(json.dumps(http_get(args.url, "/summary"), indent=2, sort_keys=True))


def cmd_sync(args: argparse.Namespace) -> None:
    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            result = sync_once(args.left_url, args.right_url)
            print(
                "synced "
                f"{args.left_url}<->{args.right_url}: "
                f"left sent {result['left_sent']}, right sent {result['right_sent']}, "
                f"applied {result['applied']}, "
                f"transferred about {result['bytes_transferred']} bytes "
                f"(attempt {attempt}/{args.retries})"
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt == args.retries:
                break
            print(f"sync attempt {attempt}/{args.retries} failed: {exc}; retrying in {args.retry_delay}s", file=sys.stderr)
            time.sleep(args.retry_delay)
    raise RuntimeError(f"sync failed after {args.retries} attempt(s): {last_error}")


def sync_once(left_url: str, right_url: str) -> dict[str, int]:
    left_summary = http_get(left_url, "/summary")
    right_summary = http_get(right_url, "/summary")

    left_missing = http_post(left_url, "/missing", {"summary": right_summary})["mutations"]
    right_missing = http_post(right_url, "/missing", {"summary": left_summary})["mutations"]

    right_applied = http_post(right_url, "/mutations", {"mutations": left_missing})["applied"]
    left_applied = http_post(left_url, "/mutations", {"mutations": right_missing})["applied"]
    bytes_transferred = len(json.dumps(left_missing, sort_keys=True).encode("utf-8")) + len(
        json.dumps(right_missing, sort_keys=True).encode("utf-8")
    )
    return {
        "left_sent": len(left_missing),
        "right_sent": len(right_missing),
        "applied": int(left_applied) + int(right_applied),
        "bytes_transferred": bytes_transferred,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PocketSync remote HTTP CLI")
    sub = parser.add_subparsers(required=True)

    update = sub.add_parser("update", help="apply a local update through one replica server")
    update.add_argument("url", help="replica URL, for example http://192.168.56.101:8001")
    update.add_argument("record")
    update.add_argument("field", nargs="+")
    update.set_defaults(func=cmd_update)

    show = sub.add_parser("show", help="show records from one replica server")
    show.add_argument("url")
    show.add_argument("record", nargs="?")
    show.set_defaults(func=cmd_show)

    summary = sub.add_parser("summary", help="show one replica's version summary")
    summary.add_argument("url")
    summary.set_defaults(func=cmd_summary)

    sync = sub.add_parser("sync", help="run pairwise anti-entropy over HTTP")
    sync.add_argument("left_url")
    sync.add_argument("right_url")
    sync.add_argument("--retries", type=int, default=1, help="number of sync attempts before giving up")
    sync.add_argument("--retry-delay", type=float, default=2.0, help="seconds to wait between failed attempts")
    sync.set_defaults(func=cmd_sync)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"remote CLI error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
