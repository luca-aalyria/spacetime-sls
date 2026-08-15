# Static / replayed weather — runbook

Operational companion to `references/weather-static-ingestion-options.md` (Options 1 & 2).
Nothing here touches the minkowski repo; the weather server is reconfigured via its
`--gfs` flag only (helm: the weather chart's args/values override).

## Option 1 — historical replay (zero infra)

For "that storm, that week" with **real** weather: do nothing. Past-time requests already
resolve to historical cycle paths, and the AWS NODD mirror (`noaa-gfs-bdp-pds`) is a deep
archive. Requirements: internet egress + consumers requesting the historical interval
(simulated clock). NOMADS retains only ~10 days; the cloud mirrors are the archive.

```
# sanity-check a cycle exists before pointing a run at it:
curl -sI https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20251012/06/atmos/gfs.t06z.pgrb2.0p25.f003.idx
```

## Option 2 — wildcard mirror (this tool)

`mirror.py` (stdlib-only Python) serves fixture GRIB2/.idx bytes under the NOAA path
grammar with the `Range` semantics the weather server requires (206 partial content;
a 200 reply to a ranged GET is a hard client error).

**Static forever:** any requested cycle path resolves to the same `wildcard.grib` /
`wildcard.idx` pair — wall-clock coupling becomes irrelevant, temporal interpolation
degenerates to identity, works air-gapped and past the 16-day horizon.

**Bounded interval:** additionally publish real per-cycle trees under the fixtures dir
(`gfs.YYYYMMDD/CC/atmos/gfs.tCCz.pgrb2.0p25.fFFF[.idx]`); exact files win over the
wildcard pair. Past-time requests need ~f000–f006 of each 6 h cycle in the interval,
plus the interpolation neighbor.

```
# 1. fixtures from a REAL NOAA pair (offsets guaranteed consistent):
mkdir -p fixtures
BASE=https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20251012/06/atmos
curl -so fixtures/wildcard.grib $BASE/gfs.t06z.pgrb2.0p25.f003        # ~500 MiB
curl -so fixtures/wildcard.idx  $BASE/gfs.t06z.pgrb2.0p25.f003.idx
# (optional) subset to the parameters the schema reads, shrinking the fixture ~50x:
#   wgrib2 wildcard.grib -match ':(TMP|SPFH|RH|PRES|HGT|CWAT|CLWMR|PRATE|UGRD|VGRD):' \
#          -grib small.grib && wgrib2 -s small.grib > small.idx
# Synthetic weather: author GRIB2 with wgrib2/cdo/pygrib, then ALWAYS regenerate the
# inventory (`wgrib2 -s file.grib > file.idx`) — offsets must match the served bytes.

# 2. run the mirror:
python3 mirror.py --fixtures fixtures --port 8082

# 3. point the weather server at it (sandboxed env / deploy override):
#      --gfs http://<mirror-host>:8082/
#    keep NOAA as fallback if egress exists: --gfs http://<mirror>:8082/,https://noaa-gfs-bdp-pds.s3.amazonaws.com/
```

Caveats (from the options doc): the `X-Forecast-Cycle` response header reports whatever
phantom cycle was requested; `python -m http.server` is NOT a substitute (no `Range`
support). Contract tests: `tests/test_gfs_wildcard_mirror.py` (8 tests, run in the venv).

## Deployment notes

- Sidecar/pod: any container with python3 (`python3 mirror.py --fixtures /etc/weather/fixtures`),
  fixtures from a ConfigMap (small synthetic GRIBs) or an init-container download.
- nginx static files also satisfy the contract natively (`Range` on by default) if you
  publish per-cycle trees; the wildcard "any cycle" behavior needs a `rewrite` to the
  fixed pair.
- Durable product path remains Option 3 (`StaticSource` in `weather/server/`, flag-selected)
  — see the options doc §4/§6.
