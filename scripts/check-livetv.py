#!/usr/bin/env python3
"""Availability check of the live TV channels: master playlist -> highest variant -> newest segment.

Reads the channels from the chart values (default kubernetes/chart/values-production.yaml) or an M3U
file. Run it from a host on the home LAN: geo-restriction depends on the connection.
Exit code 1 if any channel fails.

    scripts/check-livetv.py [--values kubernetes/chart/values-production.yaml | --m3u channels.m3u]
"""
import argparse
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}


def get(url, limit=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return r.status, r.geturl(), (r.read(limit) if limit else r.read())


def channels_from_values(path):
    import yaml  # PyYAML; in the validate venv
    data = yaml.safe_load(Path(path).read_text())
    return [(c["name"], c["url"]) for c in (data.get("liveTv") or {}).get("channels", [])]


def channels_from_m3u(path):
    lines = Path(path).read_text().splitlines()
    out = []
    for i, ln in enumerate(lines):
        if ln.startswith("#EXTINF"):
            out.append((ln.rsplit(",", 1)[1], next(x for x in lines[i + 1:] if x and not x.startswith("#"))))
    return out


def check(url):
    st, final, body = get(url)
    text = body.decode("utf-8", "replace")
    res = "-"
    if "#EXT-X-STREAM-INF" in text:
        lines = text.splitlines()
        best, bw = None, -1
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                b = int(ln.split("BANDWIDTH=")[1].split(",")[0]) if "BANDWIDTH=" in ln else 0
                if b > bw:
                    nxt = next(x for x in lines[i + 1:] if x.strip() and not x.startswith("#"))
                    best, bw = urllib.parse.urljoin(final, nxt.strip()), b
                    res = ln.split("RESOLUTION=")[1].split(",")[0] if "RESOLUTION=" in ln else "-"
        st, final, body = get(best)
        text = body.decode("utf-8", "replace")
    segs = [urllib.parse.urljoin(final, s.strip()) for s in text.splitlines() if s.strip() and not s.startswith("#")]
    if not segs:
        raise RuntimeError("no segments")
    sst, _, data = get(segs[-1], 200000)
    return f"{res} segment {sst} {len(data)}B"


def main():
    ap = argparse.ArgumentParser(description="Check the live TV channels.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--values", default="kubernetes/chart/values-production.yaml")
    g.add_argument("--m3u")
    args = ap.parse_args()
    chans = channels_from_m3u(args.m3u) if args.m3u else channels_from_values(args.values)
    failed = 0
    for name, url in chans:
        t0 = time.time()
        try:
            print(f"OK    {name:28s} {check(url)} {time.time() - t0:.1f}s")
        except Exception as exc:  # report every channel
            failed += 1
            print(f"FAIL  {name:28s} {type(exc).__name__}: {str(exc)[:80]}")
    print(f"{len(chans) - failed}/{len(chans)} channels OK")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
