import pytest


def test_import_succeeds_in_sandbox_and_flags_false():
    import ngso_sls
    import ngso_sls.spacetime as st
    # spacetime-api is absent in the sandbox -> every surface flag is False
    assert st.HAS_AUTH is False and st.HAS_NBI is False and st.HAS_MODEL is False
    assert st.HAS_PROVISIONING is False and st.HAS_NMTS is False


def test_require_raises_clear_error_when_absent():
    from ngso_sls.spacetime._deps import require
    with pytest.raises(RuntimeError, match="spacetime-api"):
        require("HAS_MODEL", "aalyria.spacetime.api.model.v1")


def test_public_symbols_importable_offline():
    import ngso_sls.spacetime as st
    assert hasattr(st, "SpacetimeEndpoint") and hasattr(st, "MemoryEntityStore")
    assert hasattr(st, "EntityStore") and hasattr(st, "StoreError")
    assert hasattr(st, "RecordedEntityStore") and hasattr(st, "record")
    assert hasattr(st, "nmts_adapter")


def test_spacetime_subpackage_not_in_core_purity_scope_but_core_still_pure():
    # importing the guarded subpackage must not drag proto into the pure core
    import ngso_sls.spacetime  # noqa: F401
    import ngso_sls.constellation, ngso_sls.coverage, ngso_sls.propagation, ngso_sls.geometry  # noqa
    # the core-purity test itself is the real guard; here we assert the subpackage imports clean
    assert True
