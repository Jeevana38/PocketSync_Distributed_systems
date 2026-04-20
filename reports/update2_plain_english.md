# Project Update 2 Draft: PocketSync

## What Changed Since Update 1

For Update 2, the design has been finalized around a smaller and more implementable version of PocketSync. The earlier design already focused on a personal-scale offline-first replicated store. The main change is that the implementation now treats the system as a small replicated job-application record store with deterministic pairwise anti-entropy, instead of trying to build a larger application or a general-purpose distributed database.

There was no special instructor feedback on Update 1, so the revisions are based on implementation progress and on keeping the project realistic for the course timeline. The current scope is: one user, a fixed set of trusted devices, full replication on every device, intermittent connectivity, and eventual convergence after devices communicate again. We still do not target sharding, dynamic membership, multi-user access control, Byzantine faults, or strong transactions.

## Finalized System Design

PocketSync has four main components on every replica.

1. Local storage: each device stores the current job records in SQLite so the user can continue reading and writing while offline.

2. Mutation log and metadata: every local edit becomes an append-only mutation with a replica id, Lamport-style counter, record id, patch, and timestamp. The mutation log is the source used for synchronization. Each replica can summarize what it has seen using a compact version summary: for each replica id, the highest counter observed.

3. Pairwise anti-entropy sync: when two replicas can communicate, they exchange summaries. Each side compares the peer summary with its local mutation log and sends only mutations the peer has not seen. The receiver stores unseen mutations and applies them through the configured conflict resolver. This avoids leader election and supports offline-first writes because any replica can accept local edits at any time.

4. Conflict resolver: PocketSync currently implements three deterministic policies. Record-level LWW is the baseline and replaces the whole record with the newest mutation. Field-wise LWW keeps a timestamp per field so independent field edits can survive. Schema-aware merge uses job-tracker semantics: descriptive fields such as company and role are mostly immutable after creation, status follows a monotonic workflow order, notes are appended without duplicate lines, and date fields keep the later date.

The key distributed systems idea is that convergence comes from anti-entropy plus deterministic merge rules, not from a central server or a leader. This is similar in spirit to eventually consistent systems like Dynamo and disconnected systems like Bayou, but simplified for a personal-scale workload.

## Implementation Progress

The current prototype is implemented in Python with only standard-library dependencies. The local replica store uses SQLite. The implementation includes:

- record and mutation models;
- SQLite tables for records and mutation logs;
- local offline updates;
- compact version summaries;
- missing-mutation detection;
- pairwise anti-entropy synchronization;
- three conflict-resolution policies;
- a deterministic experiment script with three replicas: laptop, phone, and tablet;
- unit tests for convergence and schema-aware conflict behavior.

This is significant progress because the core synchronization path now works end to end: a device can create a record, other devices can receive it, all devices can make concurrent offline edits, and a later sync round can converge them.

## Preliminary Results

The preliminary experiment creates three replicas and one job application record. After an initial sync, the replicas are partitioned logically: laptop updates the status and notes, phone updates the deadline and notes, and tablet updates last-contacted and notes. The replicas then run pairwise anti-entropy.

The early result is that all three policies converge after synchronization, but they preserve different amounts of user intent.

| Policy | Converged | Anti-entropy rounds | Mutations transferred | Structured fields preserved | Note lines preserved |
| --- | --- | ---: | ---: | ---: | ---: |
| Record-level LWW | Yes | 3 | 6 | 1 / 3 | 1 |
| Field-wise LWW | Yes | 3 | 6 | 3 / 3 | 1 |
| Schema-aware merge | Yes | 3 | 6 | 3 / 3 | 4 |

Record-level LWW converges, but it loses unrelated concurrent edits because the newest record version overwrites the whole record. Field-wise LWW preserves independent structured fields better because each field is resolved separately. Schema-aware merge preserves the structured fields and also keeps multiple note updates by appending note lines with a deterministic order. The deterministic ordering is important because two replicas must not merely preserve the same note contents; they must produce the same final value after seeing the same set of mutations.

These results are preliminary because they come from a small deterministic workload, not the full evaluation. For the final report, the evaluation should include more records, repeated randomized offline windows, injected delay/loss, convergence latency, bytes or mutations transferred, and lost-update rate.

## Work Attribution

Jeevana Kalvakuntla: led the replication design, conflict-resolution policies, and the first working prototype structure. Also drafted the Update 2 system design and preliminary evaluation explanation.

Divya Sai Sindhuja Vankineni: responsible for strengthening the local storage layer, peer communication/test harness, and helping extend the experiment workloads for the final evaluation.

Both team members will continue debugging, running experiments, and writing the final evaluation.
