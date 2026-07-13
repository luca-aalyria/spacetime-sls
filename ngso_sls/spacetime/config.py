"""Connection configuration for a Spacetime/Minkowski instance (pure Python, no proto)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SpacetimeEndpoint:
    url: str                                   # https://<host>:443
    key_id: str
    user_id: str                               # service-account id/email (see open questions)
    # Provide the private key ONE of two ways (prefer the second on Colab):
    private_key_file: str | None = None        # path to a key file on disk, OR
    private_key_b64: str | None = None         # BASE64-encoded key contents (e.g. a Colab secret:
                                               # `base64 -w0 key.pem`), decoded at use. Robust for
                                               # multi-line PEM in a single-line secret; never
                                               # written to persistent disk. The fallback auth path
                                               # uses the decoded bytes directly; the modern path
                                               # materializes a RAM-backed 0600 temp file, shredded
                                               # when the store closes.
    model_url: str | None = None               # Model service may live on a different host
    api_variant: str = "modern"                # 'modern' | 'legacy'
    model_version: str = "v1"                  # 'v1' | 'v1alpha' | 'v0'
