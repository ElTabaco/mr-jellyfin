#!/usr/bin/env python3
"""Apply the verified AMD VA-API transcoding settings to Jellyfin (idempotent).

The values come from the Phase 4 measurements in docs/hardware-compatibility.md. Only codecs that
vainfo AND real ffmpeg runs confirmed on the Radeon 780M are enabled for hardware decoding.

Usage (from a LAN host; key never on argv):
    JELLYFIN_API_KEY=... scripts/configure-transcoding.py [--url http://192.168.0.5:8096] [--dry-run]
    or: scripts/configure-transcoding.py < keyfile   (key read from stdin when the env var is unset)
"""
import argparse
import json
import os
import sys
import urllib.request

SETTINGS = {
    "HardwareAccelerationType": "vaapi",
    "VaapiDevice": "/dev/dri/renderD128",
    # Verified hardware decode: H.264, HEVC 8/10-bit, VP9 (profile 0/2), AV1.
    # NOT supported by VCN 4.0 / radeonsi: MPEG-2, VC-1, VP8 -> software decode.
    "HardwareDecodingCodecs": ["h264", "hevc", "vp9", "av1"],
    "EnableDecodingColorDepth10Hevc": True,
    "EnableDecodingColorDepth10Vp9": True,
    "EnableDecodingColorDepth10HevcRext": False,
    "EnableDecodingColorDepth12HevcRext": False,
    "PreferSystemNativeHwDecoder": True,
    "EnableHardwareEncoding": True,
    # H.264 output reaches every client; HEVC/AV1 hardware encoding works but stays off until the
    # client devices are confirmed (Phase 6).
    "AllowHevcEncoding": False,
    "AllowAv1Encoding": False,
    # HDR -> SDR tone mapping failed in the pod (Vulkan/libplacebo: DRM format modifier error;
    # tonemap_vaapi: no output format). The library has no HDR content (2026-11-11). Off.
    "EnableTonemapping": False,
    "EnableVppTonemapping": False,
}


def main():
    ap = argparse.ArgumentParser(description="Apply the verified AMD VA-API transcoding settings.")
    ap.add_argument("--url", default=os.environ.get("JELLYFIN_URL", "http://192.168.0.5:8096"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("JELLYFIN_API_KEY") or sys.stdin.readline().strip()
    if not key:
        sys.exit("JELLYFIN_API_KEY not set and nothing on stdin")
    headers = {"Authorization": f'MediaBrowser Token="{key}"', "Content-Type": "application/json"}

    def call(method, path, body=None):
        req = urllib.request.Request(args.url + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    cfg = call("GET", "/System/Configuration/encoding") or {}
    changes = {k: (cfg.get(k), v) for k, v in SETTINGS.items() if cfg.get(k) != v}
    for k, (old, new) in changes.items():
        print(f"{k}: {old!r} -> {new!r}")
    if not changes:
        print("encoding settings already as verified")
        return
    if args.dry_run:
        print("dry run, nothing written")
        return
    cfg.update(SETTINGS)
    call("POST", "/System/Configuration/encoding", cfg)
    after = call("GET", "/System/Configuration/encoding") or {}
    bad = [k for k, v in SETTINGS.items() if after.get(k) != v]
    if bad:
        sys.exit(f"not applied: {bad}")
    print(f"applied {len(changes)} setting(s)")


if __name__ == "__main__":
    main()
