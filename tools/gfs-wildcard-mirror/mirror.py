#!/usr/bin/env python3
"""Wildcard GFS mirror: serve fixed GRIB2/.idx fixtures under the NOAA GFS path grammar.

Implements Option 2 of references/weather-static-ingestion-options.md. The Spacetime
weather server treats its --gfs upstream as a content-addressable store: the path
encodes (cycle, forecast hour) and the .idx encodes parameter -> byte range. Any HTTP
server honoring that grammar plus single-range `Range:` semantics is indistinguishable
from NOAA. This one is stdlib-only so it runs anywhere Python does.

Weather-server contract (weather/server/gfs.go):
  - `<path>.idx`  : plain GET, must return 200 with the GRIB inventory.
  - `<path>`      : GET with `Range: bytes=a-b` or `bytes=a-`, MUST return 206
                    (a 200 full-content reply is a hard error in the client).
  - 404           : client falls through to the next mirror in --gfs.

Resolution order for a GFS-grammar request:
  1. exact file under --fixtures (bounded-interval mode: publish real per-cycle trees
     like `gfs.20261005/06/atmos/gfs.t06z.pgrb2.0p25.f003[.idx]`), else
  2. the wildcard pair --fixtures/wildcard.grib + wildcard.idx (static-forever mode:
     every requested cycle resolves to the same bytes; temporal interpolation
     degenerates to identity), else
  3. 404.

The .idx byte offsets must match the GRIB actually served (use a real NOAA pair, or
regenerate the inventory with `wgrib2 -s`). See README.md for fixture preparation.

Usage:
  python3 mirror.py --fixtures /etc/weather/fixtures --port 8082
  # then point the weather server at it:  --gfs http://localhost:8082/
"""
import argparse
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# gfs.YYYYMMDD/CC/atmos/gfs.tCCz.<variant>.fFFF[.idx]   (variant e.g. pgrb2.0p25)
GFS_PATH_RE = re.compile(
    r"^gfs\.(?P<ymd>\d{8})/(?P<cc>\d{2})/atmos/"
    r"gfs\.t(?P<cc2>\d{2})z\.(?P<variant>[A-Za-z0-9.]+)\.f(?P<fff>\d{3})(?P<idx>\.idx)?$")

RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$")


class GFSMirrorHandler(BaseHTTPRequestHandler):
    fixtures = "."          # set via serve()
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = self.path.lstrip("/").split("?")[0]
        if path in ("healthz", "readyz", "livez"):
            return self._send_bytes(b"ok\n", "text/plain")

        m = GFS_PATH_RE.match(path)
        if not m:
            return self._send_404(f"not a GFS path: {path!r}")

        fixture = self._resolve(path, is_idx=bool(m.group("idx")))
        if fixture is None:
            return self._send_404(f"no fixture for {path!r}")

        with open(fixture, "rb") as f:
            data = f.read()
        if m.group("idx"):
            return self._send_bytes(data, "text/plain")
        return self._send_ranged(data)

    def _resolve(self, path, is_idx):
        # 1. exact per-cycle file (bounded-interval mode)
        exact = os.path.realpath(os.path.join(self.fixtures, path))
        if exact.startswith(os.path.realpath(self.fixtures) + os.sep) and os.path.isfile(exact):
            return exact
        # 2. wildcard pair (static-forever mode)
        wild = os.path.join(self.fixtures, "wildcard.idx" if is_idx else "wildcard.grib")
        return wild if os.path.isfile(wild) else None

    def _send_ranged(self, data):
        rng = self.headers.get("Range")
        if rng is None:
            return self._send_bytes(data, "application/octet-stream")
        m = RANGE_RE.match(rng.strip())
        if not m:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(data)}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start = int(m.group(1))
        # RFC 7233: last-byte-pos is inclusive; empty means to EOF
        end = int(m.group(2)) if m.group(2) else len(data) - 1
        end = min(end, len(data) - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(data)}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        chunk = data[start:end + 1]
        self.send_response(206)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(chunk)

    def _send_bytes(self, data, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def _send_404(self, why):
        body = (why + "\n").encode()
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def serve(fixtures, port, bind="0.0.0.0"):
    handler = type("Handler", (GFSMirrorHandler,), {"fixtures": fixtures})
    httpd = ThreadingHTTPServer((bind, port), handler)
    return httpd


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixtures", required=True,
                    help="Fixture dir: wildcard.grib/wildcard.idx and/or per-cycle gfs.*/ trees")
    ap.add_argument("--port", type=int, default=8082)
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()
    httpd = serve(args.fixtures, args.port, args.bind)
    sys.stderr.write(f"GFS wildcard mirror on :{args.port}, fixtures={args.fixtures}\n")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
