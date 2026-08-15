# Contract tests for tools/gfs-wildcard-mirror/mirror.py against the weather-server
# client behavior in minkowski weather/server/gfs.go: .idx via plain GET->200,
# GRIB via single-range Range->206 (200 would be a client-side hard error), 404 fallthrough.
import http.client
import importlib.util
import os
import sys
import threading

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "gfs_mirror", os.path.join(os.path.dirname(__file__), "..",
                               "tools", "gfs-wildcard-mirror", "mirror.py"))
mirror = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mirror)

GRIB = bytes(range(256)) * 4          # 1024 content-agnostic bytes
IDX = b"1:0:d=2026101500:TMP:surface:anl:\n2:512:d=2026101500:PRATE:surface:anl:\n"
PATH = "/gfs.20991231/18/atmos/gfs.t18z.pgrb2.0p25.f003"   # arbitrary future cycle


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    fixtures = tmp_path_factory.mktemp("fixtures")
    (fixtures / "wildcard.grib").write_bytes(GRIB)
    (fixtures / "wildcard.idx").write_bytes(IDX)
    # exact per-cycle override (bounded-interval mode)
    cyc = fixtures / "gfs.20261005" / "06" / "atmos"
    cyc.mkdir(parents=True)
    (cyc / "gfs.t06z.pgrb2.0p25.f000").write_bytes(b"EXACT-GRIB")
    (cyc / "gfs.t06z.pgrb2.0p25.f000.idx").write_bytes(b"1:0:d=2026100506:TMP:surface:anl:\n")
    httpd = mirror.serve(str(fixtures), port=0, bind="127.0.0.1")
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address
    httpd.shutdown()


def _get(addr, path, headers=None):
    conn = http.client.HTTPConnection(*addr)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def test_idx_plain_get_200_for_any_cycle(server):
    resp, body = _get(server, PATH + ".idx")
    assert resp.status == 200 and body == IDX


def test_grib_range_returns_206_with_exact_slice(server):
    resp, body = _get(server, PATH, {"Range": "bytes=100-199"})
    assert resp.status == 206
    assert body == GRIB[100:200]                      # inclusive last-byte-pos
    assert resp.getheader("Content-Range") == f"bytes 100-199/{len(GRIB)}"


def test_grib_open_ended_range_to_eof(server):
    resp, body = _get(server, PATH, {"Range": "bytes=1000-"})
    assert resp.status == 206 and body == GRIB[1000:]


def test_any_phantom_cycle_resolves_to_same_bytes(server):
    _, b1 = _get(server, "/gfs.20300101/00/atmos/gfs.t00z.pgrb2.0p25.f120",
                 {"Range": "bytes=0-15"})
    _, b2 = _get(server, PATH, {"Range": "bytes=0-15"})
    assert b1 == b2 == GRIB[:16]                      # static-forever: identical everywhere


def test_exact_per_cycle_fixture_wins_over_wildcard(server):
    resp, body = _get(server, "/gfs.20261005/06/atmos/gfs.t06z.pgrb2.0p25.f000",
                      {"Range": "bytes=0-"})
    assert resp.status == 206 and body == b"EXACT-GRIB"


def test_non_gfs_path_404_for_mirror_fallthrough(server):
    resp, _ = _get(server, "/not/a/gfs/path")
    assert resp.status == 404


def test_unsatisfiable_range_416(server):
    resp, _ = _get(server, PATH, {"Range": f"bytes={len(GRIB) + 10}-"})
    assert resp.status == 416


def test_healthz(server):
    resp, body = _get(server, "/healthz")
    assert resp.status == 200 and body == b"ok\n"
