# PocketSync

PocketSync is a small offline-first replicated record store for structured personal records. The motivating workload is a job application tracker: one user owns a few devices, each device can edit records while offline, and replicas later synchronize without a central database.

The code is intentionally compact so it is easy to explain in a project update or demo. It implements the main distributed systems pieces from the report:

- Full local replicas backed by SQLite.
- Append-only mutation logs with per-replica Lamport counters.
- Pairwise anti-entropy synchronization using compact version summaries.
- Three deterministic conflict policies:
  - `record_lww`: newest mutation wins for the whole record.
  - `field_lww`: newest mutation wins independently per field.
  - `schema_aware`: uses job-tracker semantics for status, notes, deadlines, and mostly immutable descriptive fields.

## Run A Demo

```bash
python3 scripts/run_experiment.py
```

The script creates three replicas, performs concurrent offline updates, synchronizes them pairwise, and prints preliminary metrics for the three merge policies.

## Project Layout

- `src/pocketsync/models.py`: shared data models and vector summary helpers.
- `src/pocketsync/store.py`: SQLite-backed replica state and mutation log.
- `src/pocketsync/resolvers.py`: conflict-resolution algorithms.
- `src/pocketsync/sync.py`: pairwise anti-entropy protocol.
- `src/pocketsync/experiment.py`: deterministic preliminary workload.
- `reports/update2_plain_english.md`: draft text for Project Update 2 before converting to LaTeX.
