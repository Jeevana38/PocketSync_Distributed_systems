#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pocketsync.models import Mutation
from pocketsync.store import ReplicaStore


def json_bytes(data: object) -> bytes:
    return json.dumps(data, sort_keys=True).encode("utf-8")


def make_handler(store: ReplicaStore):
    class ReplicaHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send({"status": "ok", "replica": store.replica_id})
                return
            if parsed.path == "/summary":
                self._send(store.summary())
                return
            if parsed.path == "/records":
                self._send(store.records())
                return
            if parsed.path.startswith("/records/"):
                record_id = parsed.path.removeprefix("/records/")
                self._send(store.get_record(record_id))
                return
            self._send_error(404, "unknown endpoint")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            data = self._read_json()
            if parsed.path == "/update":
                mutation = store.local_update(data["record_id"], data["patch"])
                self._send({"applied": True, "mutation": mutation.to_dict()})
                return
            if parsed.path == "/missing":
                peer_summary = {key: int(value) for key, value in data.get("summary", {}).items()}
                mutations = [mutation.to_dict() for mutation in store.missing_since(peer_summary)]
                self._send({"mutations": mutations, "bytes": len(json_bytes(mutations))})
                return
            if parsed.path == "/mutations":
                mutations = [Mutation.from_dict(item) for item in data.get("mutations", [])]
                applied = store.apply_many(mutations)
                self._send({"applied": applied})
                return
            self._send_error(404, "unknown endpoint")

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[{store.replica_id}] {self.address_string()} - {fmt % args}")

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _send(self, data: object, status: int = 200) -> None:
            body = json_bytes(data)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: int, message: str) -> None:
            self._send({"error": message}, status=status)

    return ReplicaHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one PocketSync HTTP replica server.")
    parser.add_argument("--replica", required=True, help="replica id, for example laptop, phone, or tablet")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db", required=True, help="path to this replica's SQLite DB")
    parser.add_argument("--policy", default="schema_aware", choices=["record_lww", "field_lww", "schema_aware"])
    args = parser.parse_args()

    store = ReplicaStore(args.db, replica_id=args.replica, policy=args.policy)
    server = HTTPServer((args.host, args.port), make_handler(store))
    print(f"PocketSync replica {args.replica} listening on http://{args.host}:{args.port} with DB {args.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down replica server")
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
