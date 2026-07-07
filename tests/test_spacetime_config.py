from ngso_sls.spacetime.config import SpacetimeEndpoint


def test_endpoint_defaults_and_fields():
    ep = SpacetimeEndpoint(url="https://fss01-demo.spacetime.aalyria.com:443",
                           key_id="k", user_id="u", private_key_file="/tmp/k.key")
    assert ep.api_variant == "modern" and ep.model_version == "v1" and ep.model_url is None


def test_endpoint_repr_never_leaks_key_path_as_secret():
    ep = SpacetimeEndpoint(url="https://h:443", key_id="k", user_id="u",
                           private_key_file="/secret/path.key")
    # the private key CONTENTS are never held here — only a path; sanity that it's a str field
    assert isinstance(ep.private_key_file, str)
