#!/bin/sh
# Server-side sampler inside the Jellyfin container (Phase 6 load test). Every 2 s:
# epoch | cgroup CPU usage_usec | cgroup memory.current | gpu_busy_percent | ffmpeg count |
# per ffmpeg process and DRM client: pid:client:engine:ns (cumulative amdgpu fdinfo counters).
DUR=${1:-360}
OUT=${2:-/cache/hermes-loadtest/samples.txt}
END=$(( $(date +%s) + DUR ))
: > "$OUT"
while [ "$(date +%s)" -lt "$END" ]; do
    ts=$(date +%s.%N)
    cpu=$(awk '/^usage_usec/{print $2}' /sys/fs/cgroup/cpu.stat)
    mem=$(cat /sys/fs/cgroup/memory.current)
    gb=$(cat /sys/class/drm/card0/device/gpu_busy_percent 2>/dev/null || echo -1)
    n=0
    eng=""
    for d in /proc/[0-9]*; do
        [ "$(cat "$d/comm" 2>/dev/null)" = "ffmpeg" ] || continue
        n=$((n + 1))
        p=${d#/proc/}
        e=$(for f in "$d"/fdinfo/*; do grep -E '^drm-(client-id|engine-[a-z0-9_]+):' "$f" 2>/dev/null; done |
            awk -v p="$p" '/^drm-client-id/{id=$2; next} {k=$1; sub(":$","",k); key=id":"k; if(!(key in s)){s[key]=$2}} END{for(k in s) printf "%s:%s:%s,", p, k, s[k]}')
        eng="$eng$e"
    done
    echo "$ts|$cpu|$mem|$gb|$n|$eng" >> "$OUT"
    sleep 2
done
echo "finished" >> "$OUT.done"
