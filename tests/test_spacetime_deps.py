import pytest


def test_import_succeeds_in_sandbox_and_flags_consistent():
    import ngso_sls
    import ngso_sls.spacetime as st
    # The spacetime-api pip package is absent in the sandbox -> pip-only surfaces are False.
    # HAS_NBI / HAS_STORAGE / HAS_NMTS may be True: vendor/spacetime_api_stubs provides
    # locally-generated stubs (bazel-layout roots api.nbi.v1alpha, proto_internal.storage,
    # nmts.v1.proto) when wired onto sys.path.
    assert st.HAS_AUTH is False and st.HAS_MODEL is False
    assert st.HAS_PROVISIONING is False
    assert isinstance(st.HAS_NBI, bool) and isinstance(st.HAS_STORAGE, bool)


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


def test_reprobe_returns_flags_dict():
    import ngso_sls.spacetime as st
    flags = st.reprobe()
    assert set(flags) == {"HAS_AUTH", "HAS_NBI", "HAS_PROVISIONING", "HAS_MODEL", "HAS_NMTS",
                          "HAS_STORAGE"}
    # pip-only surfaces stay False in the sandbox; HAS_NBI flips True iff the vendored
    # stubs (vendor/spacetime_api_stubs) are on sys.path.
    assert flags["HAS_AUTH"] is False and flags["HAS_MODEL"] is False


def test_nbi_stubs_when_vendored():
    # With vendor/spacetime_api_stubs on sys.path (venv .pth / Colab sys.path.insert),
    # the NetOps surface is fully usable offline: real generated messages, real enum values.
    from ngso_sls.spacetime import _deps
    if not _deps.HAS_NBI:
        pytest.skip("vendored NBI stubs not on sys.path")
    pb = _deps.nbi_pb2
    assert pb.EntityType.Value("INTENT") == 6      # matches storage EntityType.INTENT
    ent = pb.Entity(id="x")
    ent.intent.SetInParent()
    assert ent.WhichOneof("value") == "intent"
    assert hasattr(_deps.nbi_pb2_grpc, "NetOpsStub")
