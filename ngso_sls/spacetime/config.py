"""Connection configuration for a Spacetime/Minkowski instance (pure Python, no proto)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SpacetimeEndpoint:
    url: str                                   # https://<host>:443
    key_id: str
    user_id: str                               # service-account id/email (see open questions)
    private_key_file: str                      # path; contents read by auth, never stored here
    model_url: str | None = None               # Model service may live on a different host
    api_variant: str = "modern"                # 'modern' | 'legacy'
    model_version: str = "v1"                  # 'v1' | 'v1alpha' | 'v0'
