#!/usr/bin/env python3
"""Phase 6 four-viewer load test against Jellyfin (synthetic clients, run from a LAN host).

Viewers (each with its own DeviceId, reported to Jellyfin as a playing session):
  1. 4K Direct Play   - static file stream, paced like a player (30 s buffer target)
  2. 1080p Direct Play - same
  3./4. 1080p -> 720p H.264 3 Mbit/s transcodes over HLS, segments fetched like a player

Per viewer: startup latency (request -> playback could start), stalls (playback position overtakes
the buffer), stall time, average delivered rate. API key from the Hermes store, never printed.

Only start/stop are reported to Jellyfin (so the viewers appear as playing sessions). Progress
reports are not sent: an API-key session has no user, and the Playback Reporting plugin (19.0)
indexes e.Users[0] in its synchronous progress handler -> ArgumentOutOfRangeException -> HTTP 400.
Real clients log in as a user and are not affected.
Usage: loadtest.py <duration_s> <json-out>
"""
import json
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "/opt/data/bin")
from hermes_secrets import get  # noqa: E402

BASE = "http://192.168.0.5:8096"
KEY = get("JELLYFIN_API_KEY")
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 300
OUT = sys.argv[2] if len(sys.argv) > 2 else "loadtest-result.json"
BUFFER_TARGET = 30.0   # seconds of media a client keeps ahead
START_BUFFER = 2.0     # seconds needed before playback starts


def hdr(dev):
    return {"Authorization": f'MediaBrowser Client="hermes-loadtest", Device="{dev}", DeviceId="{dev}", '
                             f'Version="1.0", Token="{KEY}"', "Content-Type": "application/json"}


def call(path, dev, method="GET", body=None, raw=False, timeout=60):
    req = urllib.request.Request(BASE + path, headers=hdr(dev), method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return data if raw else (json.loads(data) if data else None)


class Viewer(threading.Thread):
    def __init__(self, name, item, mode):
        super().__init__(daemon=True)
        self.name_, self.item, self.mode = name, item, mode
        self.dev = f"hermes-{name}"
        self.res = {"viewer": name, "mode": mode, "item": item["Name"], "errors": []}

    def report(self, kind, pos, ps, method):
        body = {"ItemId": self.item["Id"], "PlaySessionId": ps, "MediaSourceId": self.item["Id"],
                "PositionTicks": int(pos * 1e7), "PlayMethod": method, "CanSeek": True, "IsPaused": False}
        try:
            call({"start": "/Sessions/Playing",
                  "stop": "/Sessions/Playing/Stopped"}[kind], self.dev, "POST", body)
        except Exception as exc:
            self.res["errors"].append(f"report {kind}: {exc}")

    def run(self):
        try:
            (self.direct if self.mode == "direct" else self.hls)()
        except Exception as exc:
            self.res["errors"].append(f"{type(exc).__name__}: {exc}")

    def finish(self, t_start, play_start, stalls, stall_time, nbytes, media_s):
        wall = time.time() - t_start
        self.res.update({"startup_s": round(play_start - t_start, 2) if play_start else None,
                         "stalls": stalls, "stall_time_s": round(stall_time, 1),
                         "wall_s": round(wall, 1), "media_buffered_s": round(media_s, 1),
                         "avg_mbit_s": round(nbytes * 8 / wall / 1e6, 2), "bytes": nbytes})

    def direct(self):
        ps = f"{self.dev}-ps"
        size = self.item["MediaSources"][0]["Size"]
        dur = self.item["RunTimeTicks"] / 1e7
        bps = size / dur  # bytes per media second
        self.res["source_mbit_s"] = round(bps * 8 / 1e6, 2)
        t0 = time.time()
        url = f"{BASE}/Videos/{self.item['Id']}/stream?static=true&mediaSourceId={self.item['Id']}&playSessionId={ps}"
        req = urllib.request.Request(url, headers=hdr(self.dev))
        nbytes, play_start, stalls, stall_time, stalled_since = 0, None, 0, 0.0, None
        self.report("start", 0, ps, "DirectPlay")
        with urllib.request.urlopen(req, timeout=60) as r:
            while time.time() - t0 < DUR:
                now = time.time()
                buffered = nbytes / bps
                played = (now - play_start - stall_time) if play_start else 0
                if play_start is None and buffered >= START_BUFFER:
                    play_start = now
                if play_start is not None:
                    if played >= buffered and stalled_since is None:
                        stalls, stalled_since = stalls + 1, now
                    elif stalled_since is not None and buffered - played >= START_BUFFER:
                        stall_time += now - stalled_since
                        stalled_since = None
                if play_start is not None and buffered - played > BUFFER_TARGET:
                    time.sleep(0.2)
                    continue
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                nbytes += len(chunk)
        self.report("stop", (time.time() - (play_start or t0)), ps, "DirectPlay")
        self.finish(t0, play_start, stalls, stall_time, nbytes, nbytes / bps)

    def hls(self):
        ps = f"{self.dev}-ps"
        q = urllib.parse.urlencode({"MediaSourceId": self.item["Id"], "VideoCodec": "h264", "AudioCodec": "aac",
                                    "MaxWidth": 1280, "VideoBitrate": 3000000, "AudioBitrate": 128000,
                                    "SegmentContainer": "ts", "PlaySessionId": ps, "DeviceId": self.dev})
        t0 = time.time()
        self.report("start", 0, ps, "Transcode")
        master = call(f"/Videos/{self.item['Id']}/main.m3u8?{q}", self.dev, raw=True).decode()
        # Jellyfin answers main.m3u8 with the media playlist directly (vod)
        lines = master.splitlines()
        segs, durs = [], []
        for i, ln in enumerate(lines):
            if ln.startswith("#EXTINF"):
                durs.append(float(ln.split(":")[1].split(",")[0]))
                segs.append(next(x for x in lines[i + 1:] if x and not x.startswith("#")))
        nbytes, buffered, play_start, stalls, stall_time, stalled_since = 0, 0.0, None, 0, 0.0, None
        seg_times = []
        idx = 0
        while time.time() - t0 < DUR and idx < len(segs):
            now = time.time()
            played = (now - play_start - stall_time) if play_start else 0
            if play_start is not None and buffered - played > BUFFER_TARGET:
                time.sleep(0.2)
                if stalled_since is None and played >= buffered:
                    stalls, stalled_since = stalls + 1, time.time()
                continue
            s0 = time.time()
            data = call(f"/Videos/{self.item['Id']}/{segs[idx]}", self.dev, raw=True, timeout=120)
            seg_times.append(time.time() - s0)
            nbytes += len(data)
            buffered += durs[idx]
            idx += 1
            now = time.time()
            if play_start is None and buffered >= START_BUFFER:
                play_start = now
            played = (now - play_start - stall_time) if play_start else 0
            if stalled_since is not None and buffered - played >= START_BUFFER:
                stall_time += now - stalled_since
                stalled_since = None
            elif play_start and stalled_since is None and played > buffered:
                stalls, stalled_since = stalls + 1, now
        self.report("stop", buffered, ps, "Transcode")
        try:
            call(f"/Videos/ActiveEncodings?deviceId={self.dev}&playSessionId={ps}", self.dev, "DELETE")
        except Exception as exc:
            self.res["errors"].append(f"stop encoding: {exc}")
        self.res["segment_fetch_s"] = {"first": round(seg_times[0], 2) if seg_times else None,
                                       "max_after_first": round(max(seg_times[1:]), 2) if len(seg_times) > 1 else None,
                                       "avg": round(sum(seg_times) / len(seg_times), 3) if seg_times else None,
                                       "count": len(seg_times)}
        self.finish(t0, play_start, stalls, stall_time, nbytes, buffered)


def main():
    admin = [u for u in call("/Users", "hermes-setup") if u["Name"] == "mr"][0]["Id"]
    items = call(f"/Items?userId={admin}&IncludeItemTypes=Movie&Recursive=true&Fields=MediaSources&searchTerm=Load%20Test",
                 "hermes-setup")["Items"]
    by = {i["Name"].replace(" (2026)", ""): i for i in items}
    print("items:", sorted(by))
    viewers = [Viewer("viewer1-4k-direct", by["Load Test 2160p"], "direct"),
               Viewer("viewer2-1080p-direct", by["Load Test 1080p A"], "direct"),
               Viewer("viewer3-1080p-transcode", by["Load Test 1080p B"], "hls"),
               Viewer("viewer4-1080p-transcode", by["Load Test 1080p C"], "hls")]
    t0 = time.time()
    for v in viewers:
        v.start()
        time.sleep(1)
    time.sleep(15)
    sess = [s for s in call("/Sessions", "hermes-setup") if (s.get("DeviceId") or "").startswith("hermes-viewer")]
    seen = [{"device": s["DeviceId"], "playing": (s.get("NowPlayingItem") or {}).get("Name"),
             "method": (s.get("PlayState") or {}).get("PlayMethod"),
             "hw": (s.get("TranscodingInfo") or {}).get("HardwareAccelerationType"),
             "video": (s.get("TranscodingInfo") or {}).get("VideoCodec"),
             "reasons": (s.get("TranscodingInfo") or {}).get("TranscodeReasons")} for s in sess]
    for v in viewers:
        v.join(DUR + 120)
    result = {"started": t0, "ended": time.time(), "duration_s": DUR, "buffer_target_s": BUFFER_TARGET,
              "sessions_seen_by_jellyfin": seen, "viewers": [v.res for v in viewers]}
    json.dump(result, open(OUT, "w"), indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
