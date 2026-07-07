"""Read-only entity store seam (netsolve `Store` pattern). Proto objects flow THROUGH as opaque
values; callers/tests never import grpc. Backends: GrpcEntityStore (live), MemoryEntityStore
(fixtures), RecordedEntityStore (replay)."""
from typing import Protocol, runtime_checkable, Any


class StoreError(Exception):
    """Normalized store error so callers/tests never import grpc. `kind` in
    {Connection, Rpc, NotFound}."""
    def __init__(self, message: str, kind: str = "Rpc"):
        super().__init__(message)
        self.kind = kind

    @classmethod
    def not_found(cls, msg: str) -> "StoreError":
        return cls(msg, kind="NotFound")

    @classmethod
    def connection(cls, msg: str) -> "StoreError":
        return cls(msg, kind="Connection")

    @classmethod
    def rpc(cls, msg: str) -> "StoreError":
        return cls(msg, kind="Rpc")


@runtime_checkable
class EntityStore(Protocol):
    """READ-ONLY surface. No create/update/delete."""
    def list_entities(self) -> list[Any]: ...
    def list_relationships(self, cel: str | None = None) -> list[Any]: ...
    def get_entity(self, entity_id: str) -> Any: ...
    def list_intents(self, states: list[str] | None = None) -> list[Any]: ...
