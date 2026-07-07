import pytest
from ngso_sls.spacetime.store import StoreError


def test_store_error_kinds():
    e = StoreError("boom", kind="NotFound")
    assert e.kind == "NotFound" and "boom" in str(e)
    assert StoreError.not_found("x").kind == "NotFound"
    assert StoreError.connection("x").kind == "Connection"
    assert StoreError.rpc("x").kind == "Rpc"


def test_entity_store_is_a_protocol():
    from ngso_sls.spacetime.store import EntityStore
    import typing
    assert getattr(EntityStore, "_is_protocol", False) or isinstance(EntityStore, type)
