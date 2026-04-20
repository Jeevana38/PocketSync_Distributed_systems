from pocketsync.store import ReplicaStore
from pocketsync.sync import sync_pair


def test_pairwise_sync_converges_with_field_lww(tmp_path):
    left = ReplicaStore(tmp_path / "left.db", "left", policy="field_lww")
    right = ReplicaStore(tmp_path / "right.db", "right", policy="field_lww")
    try:
        left.local_update("job-1", {"company": "Acme", "status": "saved"})
        sync_pair(left, right)

        left.local_update("job-1", {"status": "interview"})
        right.local_update("job-1", {"next_deadline": "2026-04-20"})
        sync_pair(left, right)

        assert left.records() == right.records()
        assert left.get_record("job-1")["status"] == "interview"
        assert left.get_record("job-1")["next_deadline"] == "2026-04-20"
    finally:
        left.close()
        right.close()


def test_schema_aware_keeps_monotonic_status_and_appends_notes(tmp_path):
    left = ReplicaStore(tmp_path / "left.db", "left", policy="schema_aware")
    right = ReplicaStore(tmp_path / "right.db", "right", policy="schema_aware")
    try:
        left.local_update("job-1", {"company": "Acme", "status": "applied", "notes": "Initial note."})
        sync_pair(left, right)

        left.local_update("job-1", {"status": "interview", "notes": "Interview scheduled."})
        right.local_update("job-1", {"status": "saved", "notes": "Phone reminder."})
        sync_pair(left, right)

        record = left.get_record("job-1")
        assert record["status"] == "interview"
        assert "Interview scheduled." in record["notes"]
        assert "Phone reminder." in record["notes"]
        assert left.records() == right.records()
    finally:
        left.close()
        right.close()
