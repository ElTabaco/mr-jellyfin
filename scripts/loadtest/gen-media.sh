#!/bin/sh
# Phase 6 load-test media, generated inside the Jellyfin pod with its ffmpeg and the GPU (VA-API).
# Synthetic pattern + temporal noise so the encoder really uses the target bitrate (CBR).
set -eu
FF=/usr/lib/jellyfin-ffmpeg/ffmpeg
OUT=/cache/hermes-loadtest
DUR=600
mkdir -p "$OUT"
cd "$OUT"
gen() { # file size rate pixfmt encoder bitrate extra...
    f=$1 s=$2 r=$3 pf=$4 enc=$5 br=$6; shift 6
    t0=$(date +%s)
    $FF -hide_banner -loglevel error -y -init_hw_device vaapi=va:/dev/dri/renderD128 -filter_hw_device va \
        -f lavfi -i "testsrc2=size=$s:rate=$r,noise=alls=12:allf=t+u" \
        -f lavfi -i "sine=frequency=440:sample_rate=48000,aformat=channel_layouts=stereo" \
        -t $DUR -vf "format=$pf,hwupload" -c:v "$enc" -rc_mode CBR -b:v "$br" -maxrate "$br" "$@" \
        -c:a aac -b:a 192k -shortest "$f"
    echo "$f: $(du -h "$f" | cut -f1), $(( $(date +%s) - t0 ))s"
}
gen loadtest-2160p-hevc10.mkv 3840x2160 25 p010 hevc_vaapi 25M -profile:v main10
gen loadtest-1080p-a.mp4 1920x1080 25 nv12 h264_vaapi 8M -profile:v high
gen loadtest-1080p-b.mp4 1920x1080 25 nv12 h264_vaapi 8M -profile:v high
gen loadtest-1080p-c.mp4 1920x1080 25 nv12 h264_vaapi 8M -profile:v high
ls -la "$OUT"
