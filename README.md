# PocketSync

PocketSync is an offline-first replicated record store for structured personal records. The motivating example is a job application tracker. A user may update job-search information from a laptop, phone, or tablet, sometimes while one or more devices are offline. PocketSync lets each device keep its own local copy of the data and later synchronize with the other replicas.

The goal is to demonstrate a distributed systems design: local replicas, offline updates, mutation logs, anti-entropy synchronization, conflict resolution, and eventual convergence.

## What Problem It Solves

Job-search data is often spread across spreadsheets, notes, reminders, emails, and job portals. If a user updates a deadline on one device and adds notes on another, it becomes hard to keep everything consistent.

PocketSync explores this question:

> Can a small personal-scale system synchronize structured records across multiple trusted devices without depending on one central cloud database?

The project focuses on one user with a few trusted devices, not many users or a large cloud service.

## Design Summary

Each device is treated as a replica.

Example:

```text
laptop replica  -> laptop.db
phone replica   -> phone.db
tablet replica  -> tablet.db
```

Each replica stores:

- the current record state,
- an append-only mutation log,
- metadata used for conflict resolution.

The databases are intentionally separate. They may temporarily contain different data while devices are offline. After synchronization, they should converge to the same logical state.

## Main Distributed Systems Ideas

PocketSync covers these concepts:

- **Replication:** every device stores a full local copy.
- **Offline-first operation:** a replica can accept local updates while disconnected.
- **Network partition tolerance:** replicas may be unable to communicate for some time.
- **Eventual consistency:** replicas may temporarily diverge but should converge after sync.
- **Anti-entropy synchronization:** replicas compare summaries and exchange missing mutations.
- **Conflict resolution:** concurrent offline edits are merged deterministically.
- **Decentralized design:** there is no central authoritative database.

PocketSync chooses availability during offline periods and eventual convergence after communication resumes.

## How Synchronization Works

Every update becomes a mutation.

Example:

```json
{
  "replica_id": "laptop",
  "counter": 2,
  "record_id": "job-1",
  "patch": {
    "status": "interview"
  },
  "timestamp": 2
}
```

The `counter` is the local update number for that replica. For example:

```text
laptop:1 = first update created by laptop
laptop:2 = second update created by laptop
phone:1  = first update created by phone
```

Each replica can create a compact version summary:

```json
{
  "laptop": 2,
  "phone": 1
}
```

This means:

> I have seen laptop updates up to laptop:2 and phone updates up to phone:1.

During sync, two replicas exchange summaries, detect missing mutations, send those missing mutations, and apply them locally.

In simple terms:

```text
1. Replica A asks what Replica B has seen.
2. Replica B asks what Replica A has seen.
3. Each side finds mutations the other side is missing.
4. They exchange missing mutations.
5. Each side applies received mutations using the selected conflict policy.
```

This is a pairwise push-pull anti-entropy protocol.

## Conflict Resolution

PocketSync implements three conflict policies.

### Record-Level LWW

`record_lww` means last writer wins for the whole record.

This is simple but can lose unrelated updates. If one device updates the deadline and another updates status, the later whole-record update may overwrite the other fields.

### Field-Wise LWW

`field_lww` means last writer wins independently per field.

This is better because a status update does not erase a deadline update. However, notes are still treated as one field, so one note update may overwrite another.

### Schema-Aware Merge

`schema_aware` uses job-application semantics.

Examples:

- notes are merged instead of overwritten,
- status follows a workflow order,
- date fields keep the later date,
- company, role, and location are treated as mostly stable after creation.

This is the default policy because it preserves more user intent for the job-tracker workload.


## VM / REST Demo

For a more realistic distributed demo, run one replica server per VM.

Example VM setup:

```text
laptop VM: <ip1>, port 8001
phone VM:  <ip2>, port 8002
tablet VM: <ip3>, port 8003
```

Create a local peer config from the example:

```bash
cp config/peers.example.json config/peers.json
```

Edit `config/peers.json` so it contains actual VM addresses:

```json
{
  "laptop": "http://<ip1>:8001",
  "phone": "http://<ip2>:8002",
  "tablet": "http://<ip3>:8003"
}
```

The real `config/peers.json` is ignored by Git so each VM can keep its own local configuration if needed. The checked-in `config/peers.example.json` shows the expected format.

### Start Servers

On the laptop VM:

```bash
python3 scripts/run_replica_server.py --replica laptop --host 0.0.0.0 --port 8001 --db laptop.db --policy schema_aware
```

On the phone VM:

```bash
python3 scripts/run_replica_server.py --replica phone --host 0.0.0.0 --port 8002 --db phone.db --policy schema_aware
```

On the tablet VM:

```bash
python3 scripts/run_replica_server.py --replica tablet --host 0.0.0.0 --port 8003 --db tablet.db --policy schema_aware
```

Check that each server is reachable:

```bash
curl http://<ip1>:8001/health
curl http://<ip2>:8002/health
curl http://<ip3>/health
```

### Create And Sync Data

Create a record on laptop:

```bash
python3 scripts/remote_cli.py update laptop job-1 company="company1" role="Distributed Systems Engineer" location="Boulder" status=saved next_deadline=2026-04-15 last_contacted=2026-04-01 notes="Found posting on LinkedIn."
```

Sync laptop with the other replicas:

```bash
python3 scripts/remote_cli.py sync laptop phone --retries 5 --retry-delay 2
python3 scripts/remote_cli.py sync laptop tablet --retries 5 --retry-delay 2
```

Make offline-style updates. Do not sync yet:

```bash
python3 scripts/remote_cli.py update laptop job-1 status=interview notes="Recruiter asked for availability."
python3 scripts/remote_cli.py update phone job-1 next_deadline=2026-04-20 notes="Added reminder from phone."
python3 scripts/remote_cli.py update tablet job-1 last_contacted=2026-04-10 notes="Prepared system design notes."
```

Show divergence:

```bash
python3 scripts/remote_cli.py show laptop job-1
python3 scripts/remote_cli.py show phone job-1
python3 scripts/remote_cli.py show tablet job-1
```

Sync after reconnection:

```bash
python3 scripts/remote_cli.py sync laptop phone --retries 5 --retry-delay 2
python3 scripts/remote_cli.py sync phone tablet --retries 5 --retry-delay 2
python3 scripts/remote_cli.py sync laptop tablet --retries 5 --retry-delay 2
```

Show convergence:

```bash
python3 scripts/remote_cli.py show laptop job-1
python3 scripts/remote_cli.py show phone job-1
python3 scripts/remote_cli.py show tablet job-1
```

## Metrics

Run the deterministic experiment:

```bash
python3 scripts/run_experiment.py
```

Run the randomized experiment:

```bash
python3 scripts/run_random_experiment.py --trials 20 --records 50 --offline-ops 200 --seed 7
```

The main metrics are:

- convergence rate,
- synchronization rounds,
- mutations transferred,
- approximate bytes transferred,
- preserved update rate,
- lost fields,
- note lines preserved.

The deterministic experiment is easier to explain. The randomized experiment is better for final evaluation.

## Inspecting SQLite Data

SQLite database files are created automatically when a replica starts or receives an update.

Examples:

```text
laptop.db
phone.db
tablet.db
```

To inspect a DB directly:

```bash
sqlite3 laptop.db
```

Then:

```sql
.tables
select * from records;
select * from mutations;
```

They are generated local runtime state.

## Project Layout

- `src/pocketsync/models.py`: mutation model and version-summary helpers.
- `src/pocketsync/store.py`: SQLite-backed replica state and mutation log.
- `src/pocketsync/resolvers.py`: conflict-resolution policies.
- `src/pocketsync/sync.py`: local pairwise anti-entropy implementation.
- `src/pocketsync/experiment.py`: deterministic evaluation workload.
- `scripts/pocketsync_cli.py`: local manual demo.
- `scripts/run_replica_server.py`: HTTP replica server for VM/REST mode.
- `scripts/remote_cli.py`: remote HTTP CLI for update/show/sync.
- `scripts/show_conflict_strategies.py`: prints the effect of each merge policy.
- `scripts/run_random_experiment.py`: randomized evaluation workload.

## Current Assumptions

- One user owns all replicas.
- Replicas are trusted and non-Byzantine.
- Devices may go offline, crash, or miss sync rounds.
- The network may delay or fail requests.
- Mutations stay in the log and can be resent later.
- The current server uses simple HTTP and no full authentication layer.
- The system provides eventual consistency, not strong consistency.

## End Goal

The end goal is to show that a small offline-first replicated system can synchronize structured personal records without a central database. The main result is that all policies can converge, but schema-aware merging preserves more useful user updates than simple last-writer-wins policies.
