from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from pocketsync.models import Mutation, Record, Summary, dominates
from pocketsync.resolvers import empty_meta, resolve


class ReplicaStore:
    def __init__(self, db_path: str | Path, replica_id: str, policy: str = "schema_aware") -> None:
        self.db_path = Path(db_path)
        self.replica_id = replica_id
        self.policy = policy
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def local_update(self, record_id: str, patch: Record) -> Mutation:
        counter = self._next_counter()
        mutation = Mutation(
            replica_id=self.replica_id,
            counter=counter,
            record_id=record_id,
            patch=dict(patch),
            timestamp=counter,
        )
        self.apply_mutation(mutation)
        return mutation

    def apply_mutation(self, mutation: Mutation) -> bool:
        if self.has_mutation(mutation.op_id):
            return False
        current, meta = self.get_record_with_meta(mutation.record_id)
        next_record, next_meta = resolve(self.policy, current, meta, mutation)
        self.conn.execute(
            "insert into mutations(op_id, replica_id, counter, record_id, patch_json, timestamp) values (?, ?, ?, ?, ?, ?)",
            (mutation.op_id, mutation.replica_id, mutation.counter, mutation.record_id, json.dumps(mutation.patch), mutation.timestamp),
        )
        self.conn.execute(
            "insert or replace into records(record_id, data_json, meta_json) values (?, ?, ?)",
            (mutation.record_id, json.dumps(next_record, sort_keys=True), json.dumps(next_meta, sort_keys=True)),
        )
        self.conn.commit()
        return True

    def apply_many(self, mutations: Iterable[Mutation]) -> int:
        applied = 0
        for mutation in mutations:
            applied += int(self.apply_mutation(mutation))
        return applied

    def summary(self) -> Summary:
        rows = self.conn.execute("select replica_id, max(counter) as counter from mutations group by replica_id").fetchall()
        return {row["replica_id"]: int(row["counter"]) for row in rows}

    def missing_since(self, peer_summary: Summary) -> list[Mutation]:
        return [mutation for mutation in self.all_mutations() if not dominates(peer_summary, mutation)]

    def all_mutations(self) -> list[Mutation]:
        rows = self.conn.execute(
            "select replica_id, counter, record_id, patch_json, timestamp from mutations order by replica_id, counter"
        ).fetchall()
        return [
            Mutation(
                replica_id=row["replica_id"],
                counter=int(row["counter"]),
                record_id=row["record_id"],
                patch=json.loads(row["patch_json"]),
                timestamp=int(row["timestamp"]),
            )
            for row in rows
        ]

    def get_record(self, record_id: str) -> Record | None:
        record, _ = self.get_record_with_meta(record_id)
        return record

    def records(self) -> dict[str, Record]:
        rows = self.conn.execute("select record_id, data_json from records order by record_id").fetchall()
        return {row["record_id"]: json.loads(row["data_json"]) for row in rows}

    def get_record_with_meta(self, record_id: str) -> tuple[Record | None, dict]:
        row = self.conn.execute("select data_json, meta_json from records where record_id = ?", (record_id,)).fetchone()
        if row is None:
            return None, empty_meta()
        return json.loads(row["data_json"]), json.loads(row["meta_json"])

    def has_mutation(self, op_id: str) -> bool:
        row = self.conn.execute("select 1 from mutations where op_id = ?", (op_id,)).fetchone()
        return row is not None

    def _next_counter(self) -> int:
        row = self.conn.execute("select max(counter) as counter from mutations where replica_id = ?", (self.replica_id,)).fetchone()
        return int(row["counter"] or 0) + 1

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists records (
                record_id text primary key,
                data_json text not null,
                meta_json text not null
            );

            create table if not exists mutations (
                op_id text primary key,
                replica_id text not null,
                counter integer not null,
                record_id text not null,
                patch_json text not null,
                timestamp integer not null
            );
            """
        )
        self.conn.commit()
