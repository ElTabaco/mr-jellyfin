# Architecture

State: Phase 1 design. Facts marked (P0) were measured in Phase 0 discovery on 2026-11-10.

## Components

```text
 LAN clients (web, Android TV, mobile, TV apps)          192.168.0.0/24
        |  HTTP :8096
        v
 MetalLB L2  192.168.0.5 (pool first-pool, announced from mr2, externalTrafficPolicy Local)
        |
        v
 k3s node mr2 ─ namespace mr-do-jellyfin (Pod Security: restricted)
   Deployment mr-do-jellyfin (1 replica, Recreate)
     init  preflight      NFS mount + library folders + first-boot config seed
     main  jellyfin 12.4  /config (local SSD) /cache (local SSD) /media (NFS, ro)
                          /transcode, /tmp (emptyDir)   GPU: devic.es/dri-render -> /dev/dri/renderD128
     side  exporter       (Phase 6) jellyfin_exporter :9594
   CronJob mr-do-jellyfin-backup  03:15 daily -> /backup (NFS mr0)
   NetworkPolicy  ingress: LAN :8096, monitoring ns, backup job
        |                                   |
        | NFSv4.1 read-only                 | NFSv4.1 rw
        v                                   v
 Synology NAS (USB volume, Phase 2)     mr0.local:/srv/nfs4/homes/mr/jellyfin/backup

 kube-system: DaemonSet generic-device-plugin (mr2 only) -> announces devic.es/dri-render
 monitoring:  Prometheus (annotation scrape) + Grafana (dashboards, CallMeBot alerts: Phase 6)
 argocd:      Applications mr-do-jellyfin, mr-do-jellyfin-gpu-device-plugin
```

## Cluster facts used by the design (P0)

| Item | Value |
|---|---|
| k3s | v1.37.2+k3s1, containerd 2.3.7, flannel, k3s network policy controller |
| mr0 | 192.168.0.200, control plane, NFS server, i5-4590T 4C, 15 GiB, 1 GbE |
| mr2 | 192.168.0.202, worker, Ryzen 7 7840HS 8C/16T, 30 GiB, 1 TB NVMe (850 GB free), 1 GbE |
| GPU | mr2 only: AMD Phoenix1 [1002:15bf] Radeon 780M, amdgpu, VCN 4.0, `/dev/dri/renderD128` root:render (GID 992), cgroup v2 |
| MetalLB | v0.16.0, pool `first-pool` 192.168.0.2-29 (L2); used .2 .4 .7 .11 .12 .20 .22 .23 |
| Traefik | 3.7.15 (k3s bundled); not used by this project |
| Argo CD | v3.4.4, project `default`, apps with automated prune + selfHeal |
| Storage classes | `local-path` only (Delete, unused); existing apps use static NFS PVs (Retain) |
| Prometheus | v3.13.1 plain deployment, annotation-based pod scrape, cAdvisor, kube-state-metrics v2.15.0, no Alertmanager, no rule files |
| Grafana | 13.1.0, dashboards provisioned from ConfigMaps in mr-do-observer |

## Storage design

| Data | Location | Why |
|---|---|---|
| Database, config, plugin config, library definitions | local PV mr2 `/var/lib/mr-jellyfin/config` | SQLite needs a local filesystem (no NFS locking issues), low latency |
| Image / metadata cache | local PV mr2 `/var/lib/mr-jellyfin/cache` | regenerable, large, local SSD |
| Transcode segments | emptyDir `/transcode` (30 GiB limit) | temporary, wiped on restart |
| Temporary files | emptyDir `/tmp` (2 GiB limit) | temporary |
| Media | Synology NFS export, read-only PV | central storage; Jellyfin never writes to it |
| Backups | mr0 NFS (`/srv/nfs4/homes/mr/jellyfin/backup`) | same pattern as other mr-do-* apps; included in mr0's monthly archive |

Database, server config and plugin config share one volume on purpose: they are one consistent
state (the database references plugin and library ids), and a backup or restore must treat them
together. They are separate directories inside it (`data/`, `config/`, `plugins/configurations/`).

Persistent volumes are never deleted by automation: PVs `Retain`, PV/PVC annotated
`helm.sh/resource-policy: keep` and `argocd.argoproj.io/sync-options: Prune=false,Delete=false`.
The Argo CD Application has no `resources-finalizer`, so deleting the Application does not cascade.

## Network and security

- Entry point: MetalLB LoadBalancer `192.168.0.5:8096`, `loadBalancerSourceRanges: 192.168.0.0/24`.
- `externalTrafficPolicy: Local`: the client IP reaches Jellyfin, so Jellyfin classifies LAN clients
  correctly (no remote bitrate limits), and NetworkPolicy ipBlocks match the real client.
- No Ingress / HTTPS: LAN-only decision, see [decisions.md](decisions.md). No public exposure, no
  port forwarding on the router.
- Pod Security `restricted` on the namespace: non-root (UID 1000), no privilege escalation, all
  capabilities dropped, seccomp RuntimeDefault, no hostPath, no privileged containers.
- GPU without privileged mode: the device plugin adds only `/dev/dri/renderD128` to the pod's
  device cgroup. A plain hostPath mount of `/dev/dri` does not work for a non-privileged
  container on cgroup v2 (device not in the runtime's allow-list) — to be confirmed in Phase 4.
- Egress is not restricted: metadata providers (TMDb etc.), the NAS, and authorized stream sources.
- `/metrics` is unauthenticated (Jellyfin design) and therefore visible on the LAN.

## Processes

- Start: preflight init container fails the pod if `/media` is not NFS or a library folder is
  missing, so Jellyfin never starts with an empty library and never "cleans" the database of
  titles that are only temporarily missing.
- Updates: Git change -> PR -> merge -> Argo CD sync. Pre-upgrade backup with `scripts/backup.sh`.
  Strategy `Recreate`: a short downtime, never two servers on one database.
- Rollback: an image rollback does not undo database migrations. Rolling back across a migration
  needs a restore of the pre-upgrade backup ([backup-recovery.md](backup-recovery.md)).
