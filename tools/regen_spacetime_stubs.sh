#!/usr/bin/env bash
# Regenerate vendor/spacetime_api_stubs from minkowski protos:
#   - api/nbi/v1alpha/nbi.proto            (NetOps intent facade — key-authed path)
#   - proto_internal/storage/storage.proto (raw Store — kubectl port-forward path, engdoc
#                                           "Storage Service, port 9999"; superset closure)
# The transitive import closure is computed dynamically, so proto drift never
# silently truncates the stub set.
#
# Requires: grpcio-tools + googleapis-common-protos in the venv; a minkowski checkout
# with both roots present (branch nbi-intent-facade for the revived nbi.proto).
#
# Usage: tools/regen_spacetime_stubs.sh [MINKOWSKI_ROOT]
set -euo pipefail

MINKOWSKI_ROOT="${1:-/workspace/minkowski_ws3}"
SLS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$SLS_ROOT/.venv"
SP="$VENV/lib/python3.14/site-packages"
OUT="$SLS_ROOT/vendor/spacetime_api_stubs"

ROOTS=(api/nbi/v1alpha/nbi.proto proto_internal/storage/storage.proto)

cd "$MINKOWSKI_ROOT"
CLOSURE=$("$VENV/bin/python" - "${ROOTS[@]}" <<'EOF'
import os, re, sys
seen = set()
def deps(path):
    if path in seen or path.startswith(("google/", "validate/")):
        return                                   # externals come from installed packages
    if not os.path.exists(path):
        sys.exit(f"missing proto: {path}")
    seen.add(path)
    for line in open(path):
        m = re.match(r'\s*import\s+(?:public\s+)?"([^"]+)"', line)
        if m:
            deps(m.group(1))
for root in sys.argv[1:]:
    deps(root)
print("\n".join(sorted(seen)))
EOF
)

rm -rf "$OUT"/api "$OUT"/nmts "$OUT"/proto_internal "$OUT"/connectivitycontract
mkdir -p "$OUT"
# shellcheck disable=SC2086
"$VENV/bin/python" -m grpc_tools.protoc \
  -I . -I "$SP" -I "$SP/grpc_tools/_proto" \
  --python_out="$OUT" --grpc_python_out="$OUT" \
  $CLOSURE

# Package markers so the bazel-layout roots (api.*, nmts.*, proto_internal.*) import
# as plain packages.
find "$OUT" -type d -exec touch {}/__init__.py \;
echo "Closure: $(echo "$CLOSURE" | wc -l) protos -> $(find "$OUT" -name '*_pb2*.py' | wc -l) modules in $OUT"
