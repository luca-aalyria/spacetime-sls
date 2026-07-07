"""In-memory EntityStore over plain JSON (offline). Mirrors crates/netsolve-spacetime MemoryStore."""
import json
import pathlib
from .store import StoreError

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class MemoryEntityStore:
    def __init__(self, entities=None, relationships=None, intents=None):
        self._entities = list(entities or [])
        self._relationships = list(relationships or [])
        self._intents = list(intents or [])

    @classmethod
    def from_fixture(cls, name: str) -> "MemoryEntityStore":
        data = json.loads((_FIXTURES / name).read_text())
        return cls(data.get("entities"), data.get("relationships"), data.get("intents"))

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntityStore":
        return cls(data.get("entities"), data.get("relationships"), data.get("intents"))

    def list_entities(self):
        return list(self._entities)

    def list_relationships(self, cel: str | None = None):
        return list(self._relationships)          # CEL filtering is a live-only concern

    def get_entity(self, entity_id: str):
        for e in self._entities:
            if (e.get("id") if isinstance(e, dict) else getattr(e, "id", None)) == entity_id:
                return e
        raise StoreError.not_found(f"entity '{entity_id}' not in MemoryEntityStore")

    def list_intents(self, states=None):
        out = self._intents
        if states is not None:
            sset = set(states)
            out = [i for i in out if (i.get("state") if isinstance(i, dict)
                                      else getattr(i, "state", None)) in sset]
        return list(out)
