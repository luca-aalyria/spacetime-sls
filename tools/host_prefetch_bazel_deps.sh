#!/usr/bin/env bash
# Run ON THE HOST (unrestricted egress). Prefetches every external dependency of
# //spacebox into a bazel repository cache on the SHARED mount, so the sandbox can
# build/run spacebox without github.com access (sandbox egress blocks github; bazel,
# BCR, googleapis and the corp BES endpoint are all reachable there).
#
# The repository cache is content-addressable (sha256) — host and sandbox bazel
# versions don't need to match for cache hits, and partial runs are resumable.
#
# Usage (host):   ~/workspace_3/spacetime-sls/tools/host_prefetch_bazel_deps.sh
# Then (sandbox): cd /workspace/minkowski_ws3 && \
#                 bazel build //spacebox --repository_cache=/workspace/.bazel-repo-cache
set -euo pipefail

REPO="${1:-$HOME/workspace_3/minkowski_ws3}"
CACHE="${2:-$HOME/workspace_3/.bazel-repo-cache}"

# bazelisk fallback if no bazel on the host
if ! command -v bazel >/dev/null; then
  echo "no bazel on PATH — fetching bazelisk"
  curl -fsSLo /tmp/bazelisk \
    https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64
  chmod +x /tmp/bazelisk
  export PATH="/tmp:$PATH"
  alias bazel=/tmp/bazelisk
  BAZEL=/tmp/bazelisk
else
  BAZEL=bazel
fi

cd "$REPO"
mkdir -p "$CACHE"
# repo credential helper (auth for apk.cgr.dev Chainguard APKs etc.)
"$BAZEL" run @tweag-credential-helper//installer --repository_cache="$CACHE" >/dev/null
# fetch = download all external repos for the targets, no compilation.
# --config release matters only for build options; deps are the same.
# Target set = everything the ephemeral-instance mission needs:
#   //spacebox                          create/destroy/update/age CLI
#   //spacebox/archon                   integration-test harness (serve/test)
#   //tools/storectl                    bulk Store export/import/delete
#   //github/tools/nbictl/cmd/nbictl    model/provisioning rsync loaders
#   //scenarios/pybuilder/...           authoritative NMTS scenario builder
#   //helm/archon:archon.experimental.push   create's IMPLICIT archon image build
#                                             (apko base: apk.cgr.dev; needs cred helper)
"$BAZEL" fetch \
  //spacebox //spacebox/archon //tools/storectl \
  //github/tools/nbictl/cmd/nbictl:nbictl \
  //scenarios/pybuilder/... \
  //helm/archon:archon.experimental.push \
  --repository_cache="$CACHE"
echo
echo "Done. Cache: $CACHE ($(du -sh "$CACHE" | cut -f1))"
echo "Sandbox can now: bazel build //spacebox --repository_cache=/workspace/.bazel-repo-cache"
