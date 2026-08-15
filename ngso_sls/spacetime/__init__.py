"""Slice E — read-only Spacetime/Minkowski NBI integration (guarded subpackage).

Proto/grpc imports are lazy (see `_deps`), so this package imports cleanly even when
`spacetime-api` is absent. Offline backends (MemoryEntityStore / RecordedEntityStore) + the
NMTS adapter work with no proto dependency; the live GrpcEntityStore requires the package."""
from ._deps import (HAS_AUTH, HAS_NBI, HAS_PROVISIONING, HAS_MODEL, HAS_NMTS, HAS_STORAGE,
                    reprobe)
from .config import SpacetimeEndpoint
from .store import EntityStore, StoreError
from .memory_store import MemoryEntityStore
from .recording import RecordedEntityStore, record
from . import nmts_adapter

__all__ = ["HAS_AUTH", "HAS_NBI", "HAS_PROVISIONING", "HAS_MODEL", "HAS_NMTS", "HAS_STORAGE",
           "reprobe", "SpacetimeEndpoint", "EntityStore", "StoreError", "MemoryEntityStore",
           "RecordedEntityStore", "record", "nmts_adapter"]
