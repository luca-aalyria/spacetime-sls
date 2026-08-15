#!/usr/bin/env bash
# sandbox_live_setup.sh — everything needed to hit a live Spacetime Store from this sandbox
# and run Jupyter on the notebooks.
#
# What it does (all steps idempotent):
#   1. Fetch kubectl into /tmp/bin  (dl.k8s.io is BLOCKED here; the GCS mirror
#      storage.googleapis.com is allowlisted, so we pull from there).
#   2. Bridge gcloud ADC -> CLI + kubectl. The sandbox has NO active gcloud account
#      (`gcloud auth list` is empty) but valid application-default credentials
#      (~/.config/gcloud/application_default_credentials.json). gcloud commands work with
#      CLOUDSDK_AUTH_ACCESS_TOKEN; kubectl works with --token. No gke-gcloud-auth-plugin needed.
#   3. Resolve the GKE endpoint + CA and emit /tmp/bin/kctl (kubectl wrapper that mints a
#      fresh ADC token per call — tokens expire hourly, so never cache one in a kubeconfig).
#   4. Start a SUPERVISED port-forward to svc/$SERVICE:9999 (re-establishes with a fresh
#      token if it drops, storectl-style).
#   5. Install JupyterLab + ipywidgets into the repo venv and launch it on $JUPYTER_PORT.
#
# Usage:
#   tools/sandbox_live_setup.sh                 # full setup + port-forward + jupyter
#   START_JUPYTER=0 tools/sandbox_live_setup.sh # tools + port-forward only
#   PROJECT=a5a-s7e-mss01-demo tools/sandbox_live_setup.sh   # another instance
#
# Then in a notebook / python:
#   from ngso_sls.spacetime.client import StorageEntityStore
#   StorageEntityStore("localhost:9999").list_intents()
#
# Stop everything:  kill $(cat /tmp/spacetime-pf.pid) ; pkill -f jupyter-lab
set -euo pipefail

PROJECT="${PROJECT:-a5a-s7e-fss01-demo}"
CLUSTER="${CLUSTER:-cluster}"
LOCATION="${LOCATION:-us-central1}"
NAMESPACE="${NAMESPACE:-spacetime}"
SERVICE="${SERVICE:-storage}"
LOCAL_PORT="${LOCAL_PORT:-9999}"
START_JUPYTER="${START_JUPYTER:-1}"
JUPYTER_PORT="${JUPYTER_PORT:-8888}"
KUBECTL_VERSION="${KUBECTL_VERSION:-v1.31.0}"

BIN=/tmp/bin
SLS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$SLS_ROOT/.venv"
CA="/tmp/gke-ca-$PROJECT.pem"
mkdir -p "$BIN"

echo "== 1/5 kubectl =="
if [ ! -x "$BIN/kubectl" ]; then
  curl -sLo "$BIN/kubectl" \
    "https://storage.googleapis.com/kubernetes-release/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl"
  chmod +x "$BIN/kubectl"
fi
"$BIN/kubectl" version --client | head -1

echo "== 2/5 ADC bridge =="
adc_token() { gcloud auth application-default print-access-token; }
CLOUDSDK_AUTH_ACCESS_TOKEN="$(adc_token)"
export CLOUDSDK_AUTH_ACCESS_TOKEN
gcloud config set project "$PROJECT" --quiet >/dev/null 2>&1 || true

echo "== 3/5 cluster endpoint + kctl wrapper =="
ENDPOINT=$(gcloud container clusters describe "$CLUSTER" --project "$PROJECT" \
  --location "$LOCATION" --format='value(endpoint)')
gcloud container clusters describe "$CLUSTER" --project "$PROJECT" --location "$LOCATION" \
  --format='value(masterAuth.clusterCaCertificate)' | base64 -d > "$CA"
cat > "$BIN/kctl" <<KCTL
#!/usr/bin/env bash
# kubectl against $PROJECT/$CLUSTER with a fresh ADC token per invocation.
exec $BIN/kubectl --server=https://$ENDPOINT --certificate-authority=$CA \\
  --token="\$(gcloud auth application-default print-access-token)" "\$@"
KCTL
chmod +x "$BIN/kctl"
"$BIN/kctl" get svc -n "$NAMESPACE" "$SERVICE" >/dev/null
echo "kctl OK -> svc/$SERVICE in ns/$NAMESPACE reachable ($ENDPOINT)"

echo "== 4/5 supervised port-forward :$LOCAL_PORT -> svc/$SERVICE:9999 =="
if [ -f /tmp/spacetime-pf.pid ] && kill -0 "$(cat /tmp/spacetime-pf.pid)" 2>/dev/null; then
  echo "already running (pid $(cat /tmp/spacetime-pf.pid))"
else
  nohup bash -c "
    while true; do
      $BIN/kctl port-forward svc/$SERVICE -n $NAMESPACE $LOCAL_PORT:9999 >> /tmp/spacetime-pf.log 2>&1
      echo \"[\$(date -u +%FT%TZ)] port-forward exited; retrying in 3s\" >> /tmp/spacetime-pf.log
      sleep 3
    done" > /dev/null 2>&1 &
  echo $! > /tmp/spacetime-pf.pid
  sleep 4
  echo "supervisor pid $(cat /tmp/spacetime-pf.pid); log /tmp/spacetime-pf.log"
fi
tail -1 /tmp/spacetime-pf.log

echo "== 5/5 jupyter =="
if [ "$START_JUPYTER" = "1" ]; then
  "$VENV/bin/pip" show jupyterlab >/dev/null 2>&1 || \
    "$VENV/bin/pip" install -q jupyterlab ipywidgets
  # /home/node is not writable in this sandbox (jupyter dies on mkdir ~/.local),
  # so give the server a private HOME under /tmp.
  mkdir -p /tmp/jupyter/home
  echo "launching JupyterLab on :$JUPYTER_PORT (root dir: $SLS_ROOT)"
  HOME=/tmp/jupyter/home exec "$VENV/bin/jupyter" lab --no-browser --ip=0.0.0.0 \
    --port="$JUPYTER_PORT" --notebook-dir="$SLS_ROOT" \
    --ServerApp.token='' --ServerApp.password=''
else
  echo "START_JUPYTER=0 -> skipping; venv python can already hit localhost:$LOCAL_PORT"
fi
