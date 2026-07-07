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
