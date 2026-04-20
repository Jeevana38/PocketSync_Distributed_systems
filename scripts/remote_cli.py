#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "peers.json"


def parse_patch(values: list[str]) -> dict[str, str]:
    patch: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid field assignment {value!r}. Use field=value.")
        key, raw = value.split("=", 1)
        patch[key.strip()] = raw.strip()
    return patch


def load_config(path: str | Path) -> dict[str, str]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return {str(key): str(value).rstrip("/") for key, value in data.items()}


def resolve_target(target: str, config: dict[str, str]) -> str:
    if target.startswith("http://") or target.startswith("https://"):
        return target.rstrip("/")
    if target in config:
        return config[target]
    raise SystemExit(
        f"Unknown replica {target!r}. Use a full URL or add it to the peer config."
    )


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
    config = load_config(args.config)
    url = resolve_target(args.target, config)
    result = http_post(url, "/update", {"record_id": args.record, "patch": parse_patch(args.field)})
    print(json.dumps(result, indent=2, sort_keys=True))


def cmd_show(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    url = resolve_target(args.target, config)
    path = f"/records/{args.record}" if args.record else "/records"
    print(json.dumps(http_get(url, path), indent=2, sort_keys=True))


def cmd_summary(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    url = resolve_target(args.target, config)
    print(json.dumps(http_get(url, "/summary"), indent=2, sort_keys=True))


def cmd_sync(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    left_url = resolve_target(args.left, config)
    right_url = resolve_target(args.right, config)
    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            result = sync_once(left_url, right_url)
            print(
                "synced "
                f"{args.left}<->{args.right}: "
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
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="peer config JSON path")
    sub = parser.add_subparsers(required=True)

    update = sub.add_parser("update", help="apply a local update through one replica server")
    update.add_argument("target", help="replica name from config or full URL")
    update.add_argument("record")
    update.add_argument("field", nargs="+")
    update.set_defaults(func=cmd_update)

    show = sub.add_parser("show", help="show records from one replica server")
    show.add_argument("target", help="replica name from config or full URL")
    show.add_argument("record", nargs="?")
    show.set_defaults(func=cmd_show)

    summary = sub.add_parser("summary", help="show one replica's version summary")
    summary.add_argument("target", help="replica name from config or full URL")
    summary.set_defaults(func=cmd_summary)

    sync = sub.add_parser("sync", help="run pairwise anti-entropy over HTTP")
    sync.add_argument("left", help="replica name from config or full URL")
    sync.add_argument("right", help="replica name from config or full URL")
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
