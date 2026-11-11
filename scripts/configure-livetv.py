#!/usr/bin/env python3
"""Register the chart's channel list as Jellyfin's M3U tuner and refresh the guide (idempotent).

The playlist is the ConfigMap file mounted in the pod (values: liveTv.mountPath + /channels.m3u).
Usage (from a LAN host; key never on argv):
    JELLYFIN_API_KEY=... scripts/configure-livetv.py [--url http://192.168.0.5:8096] [--dry-run]
    or pipe the key on stdin when the env var is unset.
With --epg-url the XMLTV guide (chart liveTv.epg, in-cluster service) is registered as listings
provider for all tuners; channels match by M3U tvg-id = XMLTV channel id.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

PLAYLIST = "/livetv/channels.m3u"
TUNER = {
    "Type": "m3u",
    "Url": PLAYLIST,
    "FriendlyName": "mr-jellyfin channels (Git)",
    "ImportFavoritesOnly": False,
    "AllowHWTranscoding": True,
    "AllowStreamSharing": True,
    "EnableStreamLooping": False,
    "TunerCount": 0,
}


def main():
    ap = argparse.ArgumentParser(description="Register the Git-managed M3U channel list in Jellyfin.")
    ap.add_argument("--url", default=os.environ.get("JELLYFIN_URL", "http://192.168.0.5:8096"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--epg-url", default=os.environ.get("JELLYFIN_EPG_URL", ""),
                    help="XMLTV URL, e.g. http://mr-do-jellyfin-epg:3000/guide.xml")
    args = ap.parse_args()
    key = os.environ.get("JELLYFIN_API_KEY") or sys.stdin.readline().strip()
    if not key:
        sys.exit("JELLYFIN_API_KEY not set and nothing on stdin")
    headers = {"Authorization": f'MediaBrowser Token="{key}"', "Content-Type": "application/json"}

    def call(method, path, body=None):
        req = urllib.request.Request(args.url + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    cfg = call("GET", "/System/Configuration/livetv") or {}
    hosts = cfg.get("TunerHosts") or []
    mine = [h for h in hosts if h.get("Type") == "m3u" and h.get("Url") == PLAYLIST]
    if mine:
        print(f"tuner exists: {mine[0].get('FriendlyName')} ({mine[0].get('Id')})")
    elif args.dry_run:
        print(f"would add M3U tuner {PLAYLIST}")
    else:
        added = call("POST", "/LiveTv/TunerHosts", TUNER) or {}
        print(f"tuner added: {added.get('Id')}")
    if args.epg_url:
        providers = cfg.get("ListingProviders") or []
        if any(p.get("Type") == "xmltv" and p.get("Path") == args.epg_url for p in providers):
            print(f"XMLTV provider exists: {args.epg_url}")
        elif args.dry_run:
            print(f"would add XMLTV provider {args.epg_url}")
        else:
            added = call("POST", "/LiveTv/ListingProviders", {"Type": "xmltv", "Path": args.epg_url,
                                                              "EnableAllTuners": True}) or {}
            print(f"XMLTV provider added: {added.get('Id')}")
    if args.dry_run:
        return
    task = next(t for t in call("GET", "/ScheduledTasks?isHidden=false") or [] if t.get("Key") == "RefreshGuide")
    call("POST", f"/ScheduledTasks/Running/{task['Id']}")
    st = task
    t0 = time.time()
    while time.time() - t0 < 600:
        time.sleep(5)
        st = next(t for t in call("GET", "/ScheduledTasks?isHidden=false") or [] if t.get("Key") == "RefreshGuide")
        if st["State"] == "Idle":
            break
    print(f"guide refresh: {st.get('LastExecutionResult', {}).get('Status')} in {int(time.time() - t0)}s")
    ch = call("GET", "/LiveTv/Channels?limit=500") or {}
    print(f"channels in Jellyfin: {ch.get('TotalRecordCount')}")
    for c in ch.get("Items", []):
        prog = call("GET", f"/LiveTv/Programs?channelIds={c['Id']}&limit=1&hasAired=false") or {}
        print(f"  {c['Name']:28s} upcoming programmes: {prog.get('TotalRecordCount', 0)}")


if __name__ == "__main__":
    main()
