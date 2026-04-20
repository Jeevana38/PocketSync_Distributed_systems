"""PocketSync: a small offline-first replicated store prototype."""

from pocketsync.store import ReplicaStore
from pocketsync.sync import sync_pair

__all__ = ["ReplicaStore", "sync_pair"]
