# Design decisions

| # | Decision | Reason | Alternatives rejected |
|---|---|---|---|
| D1 | Own lean Helm chart in this repo | Static Retain PVs (local + NFS with mount options), device-plugin resource, Recreate strategy, preflight, backup CronJob; no new Helm repository in Argo CD | Official `jellyfin/jellyfin-helm` 3.7.0 as dependency (maintained, but: inline NFS without mount options, no static PV, RollingUpdate default, new Helm repo) |
| D2 | Run on mr2, pinned by node selector + local PVs | Only node with an AMD GPU; NVMe for database/cache | mr0 (Intel Haswell iGPU, 4 cores) |
| D3 | `Recreate`, 1 replica | SQLite database must never be opened by two servers | RollingUpdate |
| D4 | Database + config + plugin config on one local volume (separate directories) | One consistent state for backup/restore; SQLite on local disk | NFS for config (SQLite locking/latency), separate PVs per directory (no gain, inconsistent backups) |
| D5 | Cache local PV, transcode + tmp emptyDir | Cache is reusable across restarts; transcode/tmp are disposable | All on one volume |
| D6 | Media NFSv4.1 read-only from the Synology NAS | Owner decision; Jellyfin never writes media | Media on mr0 system disk |
| D7 | Preflight init container | No start without media: avoids an empty library and avoids Jellyfin removing items that are only temporarily missing | Start regardless |
| D8 | MetalLB LoadBalancer `192.168.0.5:8096`, `externalTrafficPolicy: Local`, no Ingress, HTTP only | Owner decision "only LAN"; TV clients and self-signed certificates do not mix; client IP preserved for LAN detection | Traefik IngressRoute + TLS (no CA/DNS name; Traefik sees node IPs with policy Cluster) |
| D9 | GPU via `squat/generic-device-plugin` exposing only `renderD128` | Non-privileged access on cgroup v2, only the needed device, approved 2026-11-10 | privileged pod, hostPath `/dev/dri` (blocked by device cgroup), ROCm device plugin (aimed at compute, exposes `/dev/kfd`), DRA driver (young project) |
| D10 | Namespace via Argo CD `managedNamespaceMetadata`, Pod Security `restricted` | One owner for the namespace, enforced pod hardening | separate `namespace.yaml` |
| D11 | Two backup methods (Jellyfin API archive + SQLite online copy) | API archive = official restore path; file copy works without API key/scans and covers config/plugins | API only (needs key, refused during scans), filesystem copy without SQLite API (inconsistent) |
| D12 | Backups to mr0 NFS like the other apps | Owner decision ("like other") | NAS |
| D13 | Metrics via annotation scrape, rules staged in `monitoring/` | Cluster Prometheus has no operator (ServiceMonitor would be ignored) | ServiceMonitor |
| D14 | Alert delivery CallMeBot (Phase 6) | Owner decision; no Alertmanager in the cluster | new Alertmanager |
| D15 | Images pinned by tag + digest, `latest` fails rendering | Reproducible deployments | tags only |
| D16 | No unlicensed sources (xStream, movie4k.to and similar) | Only content the owner is authorized to stream | - |
