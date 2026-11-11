#!/usr/bin/env python3
"""Analyse the Phase 6 load test: in-pod samples (sampler.sh) + Prometheus over the test window.
Usage: analyze.py samples.txt result.json"""
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

PROM = "http://192.168.0.12:9090"
samples_file, result_file = sys.argv[1], sys.argv[2]
res = json.load(open(result_file))
t_start, t_end = res["started"], res["ended"]

rows = []
for ln in open(samples_file):
    parts = ln.rstrip("\n").split("|")
    if len(parts) < 6:
        continue
    ts, cpu, mem, gb, n, eng = parts
    e = {}
    for item in filter(None, eng.split(",")):
        pid, client, engine, ns = item.split(":")
        e[(pid, client, engine)] = int(ns)
    rows.append((float(ts), int(cpu), int(mem), int(gb), int(n), e))
rows = [r for r in rows if t_start <= r[0] <= t_end]

cores, eng_util, gpu_busy, ffm = [], defaultdict(list), [], []
for a, b in zip(rows, rows[1:]):
    dt = b[0] - a[0]
    cores.append((b[1] - a[1]) / 1e6 / dt)
    gpu_busy.append(b[3])
    ffm.append(b[4])
    per = defaultdict(float)
    for k, v in b[5].items():
        if k in a[5] and v >= a[5][k]:
            per[k[2]] += (v - a[5][k]) / 1e9 / dt
    for eng, u in per.items():
        eng_util[eng].append(u)


def stats(xs, scale=1.0, nd=2):
    if not xs:
        return None
    xs = sorted(x * scale for x in xs)
    return {"avg": round(sum(xs) / len(xs), nd), "p95": round(xs[int(0.95 * (len(xs) - 1))], nd),
            "max": round(xs[-1], nd)}


def prom_range(q):
    url = f"{PROM}/api/v1/query_range?" + urllib.parse.urlencode(
        {"query": q, "start": t_start + 30, "end": t_end, "step": 15})
    r = json.load(urllib.request.urlopen(url, timeout=30))["data"]["result"]
    return [float(v[1]) for s in r for v in s["values"]]


node_cpu = prom_range('sum(rate(container_cpu_usage_seconds_total{id="/", node="mr2"}[1m]))')
net_tx = prom_range('sum(rate(container_network_transmit_bytes_total{namespace="mr-do-jellyfin", '
                    'pod=~"mr-do-jellyfin-[a-z0-9]+-[a-z0-9]+"}[1m])) * 8 / 1e6')
net_rx = prom_range('sum(rate(container_network_receive_bytes_total{namespace="mr-do-jellyfin", '
                    'pod=~"mr-do-jellyfin-[a-z0-9]+-[a-z0-9]+"}[1m])) * 8 / 1e6')
node_mem = prom_range('container_memory_working_set_bytes{id="/", node="mr2"} / 1024 / 1024 / 1024')

summary = {
    "samples": len(rows),
    "jellyfin_pod_cpu_cores": stats(cores),
    "jellyfin_pod_memory_mib_max": round(max(r[2] for r in rows) / 2**20) if rows else None,
    "ffmpeg_processes": stats(ffm, nd=1),
    "gpu_busy_percent_gfx": stats(gpu_busy, nd=1),
    "gpu_engine_busy_fraction": {k: stats(v, nd=3) for k, v in sorted(eng_util.items())},
    "mr2_node_cpu_cores_of_16": stats(node_cpu),
    "mr2_node_memory_gib": stats(node_mem),
    "pod_network_tx_mbit_s": stats(net_tx, nd=1),
    "pod_network_rx_mbit_s": stats(net_rx, nd=1),
}
res["server"] = summary
json.dump(res, open(result_file, "w"), indent=2)
print(json.dumps(summary, indent=2))
