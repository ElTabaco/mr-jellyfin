# mr-jellyfin

Self-hosted streaming platform for the mr home lab: one [Jellyfin](https://jellyfin.org) server on the
k3s cluster, deployed by Argo CD from this repository. LAN only.

| | |
|---|---|
| Argo CD application | `mr-do-jellyfin` (`kubernetes/application.yaml`) |
| Namespace | `mr-do-jellyfin` (created by Argo CD, Pod Security `restricted`) |
| Jellyfin | 12.4, image `docker.io/jellyfin/jellyfin:12.4.20261026-211555@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771` |
| URL | `http://192.168.0.5:8096` (MetalLB, LAN `192.168.0.0/24` only, plain HTTP) |
| Node | `mr2` (AMD Ryzen 7 7840HS, Radeon 780M iGPU, VCN 4.0) |
| Media | Synology DS220+ `riemerkNASS.local:/volumeUSB1/usbshare/media` (USB SSD, 458 GB) over NFSv4.1, read-only |
| State | node-local SSD on mr2: `/var/lib/mr-jellyfin/{config,cache}` |
| Backups | daily 03:15 Europe/Zurich to `mr0.local:/srv/nfs4/homes/mr/jellyfin/backup`, 14 kept |
| Status | Phase 4: running with AMD VA-API hardware transcoding: see [docs/phase-log.md](docs/phase-log.md) |

## Repository layout

```text
README.md                         this file (all ports, paths, values)
docs/
  architecture.md                 components, data flow, storage, network, security
  installation.md                 host preparation + first deployment (Phases 2-4)
  operations.md                   daily operation, upgrades, rollback, users, API keys
  troubleshooting.md              symptoms -> checks -> fixes
  backup-recovery.md              backup design, restore, disaster recovery, restore test
  hardware-compatibility.md       GPU / VA-API report (Phase 0 facts, Phase 4 measurements)
  plugins-and-sources.md          online sources: supported / candidate / not supported
  decisions.md                    design decisions and their reasons
  phase-log.md                    phases, approvals, open items
kubernetes/
  application.yaml                Argo CD Application (Helm chart below)
  apply.sh                        registers the Application(s) (run on mr0)
  chart/                          Helm chart mr-do-jellyfin
    Chart.yaml
    values.yaml                   defaults (documented below)
    values-production.yaml        mr home lab values (node, IP, NAS, paths)
    ci/test-values.yaml           validation-only values (documentation domains/IPs)
    files/preflight.sh            init container: NFS + library checks, first-boot config seed
    files/backup.py               backup CronJob
    files/restore.py              restore pod (used by scripts/restore.sh)
    templates/                    Deployment, Service, PV/PVC, NetworkPolicy, CronJob, ConfigMap
  platform/gpu-device-plugin/     separate Argo CD app: generic-device-plugin (renderD128 on mr2)
monitoring/
  alerts.yaml                     Prometheus rules (staged for mr-do-observer, Phase 6)
  alerts.test.yaml                promtool unit tests
  README.md
plugins/README.md                 plugin policy and evaluation checklist
scripts/
  validate.sh                     static validation (lint, render, schemas, policy, rules, scripts, secrets)
  policy_check.py                 pinned images, Retain/keep storage, no privileged pods
  backup.sh                       run a backup now (pre-upgrade), wait for result
  restore.sh                      list / restore files backup / stage API archive
  healthcheck.sh                  HTTP + Kubernetes + Argo CD health
  check-no-secrets.sh             secret scan (CI)
  configure-transcoding.py        apply the verified VA-API settings through the Jellyfin API
  configure-livetv.py             register the Git channel list as M3U tuner, refresh the guide
  check-livetv.py                 availability check of every live TV channel (run on the LAN)
.github/workflows/                validate.yml, check-secrets.yml
```

## Network and ports

| Port | Protocol | Where | Purpose |
|---|---|---|---|
| 8096 | TCP/HTTP | Service `mr-do-jellyfin` (LoadBalancer `192.168.0.5`, pool `first-pool`) -> container `http` | Web UI, API, clients, `/health`, `/metrics` |
| 9594 | TCP/HTTP | exporter sidecar (only if `exporter.enabled`) | jellyfin_exporter metrics for Prometheus |
| 8080 | TCP/HTTP | generic-device-plugin pod (kube-system, mr2) | plugin health/metrics (not exposed) |

- `externalTrafficPolicy: Local`: client IP preserved (Jellyfin LAN detection), IP announced from mr2.
- `loadBalancerSourceRanges: 192.168.0.0/24` and a NetworkPolicy (LAN CIDR, `monitoring` namespace, backup job).
- No Ingress, no HTTPS, no port forwarding (decision: LAN only, plain HTTP; [docs/decisions.md](docs/decisions.md)).
- Not available behind a LoadBalancer: UDP 7359 client auto-discovery and DLNA (need host networking). Clients connect with `http://192.168.0.5:8096`.

## Storage

| Volume | Mount | Kind | Node / server path | Size | Access |
|---|---|---|---|---|---|
| `mr-do-jellyfin-pvc-config` | `/config` | local PV, Retain | mr2 `/var/lib/mr-jellyfin/config` | 20Gi | RWO |
| `mr-do-jellyfin-pvc-cache` | `/cache` | local PV, Retain | mr2 `/var/lib/mr-jellyfin/cache` | 50Gi | RWO |
| `mr-do-jellyfin-pvc-media` | `/media` | NFS PV, Retain | `riemerkNASS.local:/volumeUSB1/usbshare/media` | 458Gi | ROX, read-only |
| `mr-do-jellyfin-pvc-backup` | `/backup` (backup job only) | NFS PV, Retain | `mr0.local:/srv/nfs4/homes/mr/jellyfin/backup` | 50Gi | RWX |
| `transcode` | `/transcode` | emptyDir | mr2 node disk | limit 30Gi | wiped on restart |
| `tmp` | `/tmp` | emptyDir | mr2 node disk | limit 2Gi | wiped on restart |

Contents of `/config` (Jellyfin data dir, official image layout):
`config/` server settings (`system.xml`, `encoding.xml`, `network.xml`, ...),
`data/jellyfin.db` database, `data/backups/` Jellyfin backup archives, `plugins/` plugins,
`plugins/configurations/` plugin settings, `root/` library definitions, `metadata/` images/NFO cache,
`log/` server logs.

Library folders expected below the NFS export (checked by the preflight init container):
`movies/`, `series/`, `documentaries/`, `home-videos/` (+ `music/` in production) -> in Jellyfin `/media/movies`,
`/media/series`, `/media/documentaries`, `/media/home-videos`, `/media/music`.

Every PV/PVC has `helm.sh/resource-policy: keep` and `argocd.argoproj.io/sync-options: Prune=false,Delete=false`;
every PV has `persistentVolumeReclaimPolicy: Retain`.

## Identity and permissions

| Item | Value |
|---|---|
| UID / GID (Jellyfin, preflight, backup, restore) | `1000` / `1000` |
| fsGroup | `1000` (`fsGroupChangePolicy: OnRootMismatch`) |
| Supplemental group with GPU | `992` = `render` on mr2 (owner group of `/dev/dri/renderD128`) |
| Owner of `/var/lib/mr-jellyfin/{config,cache}` on mr2 | `1000:1000`, mode `0750` (Phase 2) |
| NAS export | read access for the mapped NFS user is enough; mounted read-only |
| Container security | non-root, `allowPrivilegeEscalation: false`, all capabilities dropped, `seccomp: RuntimeDefault`, no privileged, no hostPath |
| GPU access | extended resource `devic.es/dri-render: 1` from the device plugin (no privileged mode) |

## Images (all pinned by tag and digest)

| Image | Tag | Digest | Used by |
|---|---|---|---|
| `docker.io/jellyfin/jellyfin` | `12.4.20261026-211555` | `sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771` | Jellyfin, preflight init |
| `docker.io/library/python` | `3.14.10-slim-trixie` | `sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f` | backup CronJob, restore pod |
| `docker.io/rebelcore/jellyfin-exporter` | `v1.6.0` | `sha256:d1985ef9ad50b8924e74ee1dd12accd64936a65150375a8e190c2293b6e2678c` | exporter sidecar (Phase 6) |
| `docker.io/squat/generic-device-plugin` | `7626d56` (release 0.2.0) | `sha256:11fa77056eb09661c08ab9760778eec7fded67b0119fff2536b064b28d1211c1` | GPU device plugin (Phase 4) |

## Environment variables

| Container | Variable | Value | Source |
|---|---|---|---|
| jellyfin | `TZ` | `Europe/Zurich` | `timeZone` |
| jellyfin | `JELLYFIN_PublishedServerUrl` | `http://192.168.0.5:8096` | `publishedServerUrl` |
| jellyfin | `JELLYFIN_DATA_DIR`, `JELLYFIN_CONFIG_DIR`, `JELLYFIN_CACHE_DIR`, `JELLYFIN_LOG_DIR`, `JELLYFIN_FFMPEG` | `/config`, `/config/config`, `/cache`, `/config/log`, `/usr/lib/jellyfin-ffmpeg/ffmpeg` | image defaults (unchanged) |
| preflight | `LIBRARIES` | `movies series documentaries home-videos` | `preflight.libraries` |
| preflight | `SEED_ENABLE_METRICS`, `SEED_TRANSCODE_PATH` | `true`, `true` | `preflight.seed*` |
| backup | `CONFIG_DIR`, `BACKUP_DIR`, `WORK_DIR` | `/config`, `/backup`, `/work` | fixed |
| backup | `KEEP`, `KEEP_LOCAL_API_ARCHIVES` | `14`, `3` | `backup.keep`, `backup.keepLocalApiArchives` |
| backup | `JELLYFIN_URL` | `http://mr-do-jellyfin.mr-do-jellyfin.svc.cluster.local:8096` | rendered |
| backup | `JELLYFIN_API_KEY` | Secret `mr-do-jellyfin-api-key` key `api-key` (optional) | created out of band |
| backup | `API_RETRIES`, `API_RETRY_SLEEP` | `3`, `120` (script defaults) | - |
| exporter | `JELLYFIN_ADDRESS`, `JELLYFIN_TOKEN` | `http://127.0.0.1:8096`, Secret `mr-do-jellyfin-api-key`/`api-key` | `exporter.*` |
| restore | `ARCHIVE`, `MODE` | archive file name, `files` or `stage-api` | `scripts/restore.sh` |

Secrets are never in Git. The only Secret is `mr-do-jellyfin-api-key` (Jellyfin admin API key), created in
Phase 3 with `kubectl create secret` ([docs/operations.md](docs/operations.md#api-key-secret)).

## Helm values

Defaults in `kubernetes/chart/values.yaml`; mr home lab overrides in `values-production.yaml`.

| Key | Default | Production | Meaning |
|---|---|---|---|
| `fullnameOverride` | `""` | - | resource name prefix (default: release name `mr-do-jellyfin`) |
| `image.repository` / `tag` / `digest` / `pullPolicy` | see Images | - | Jellyfin image; `latest` and missing digest fail rendering |
| `timeZone` | `Europe/Zurich` | - | TZ for Jellyfin and the backup schedule |
| `publishedServerUrl` | `""` | `http://192.168.0.5:8096` | URL in discovery replies |
| `nodeSelector` | `{}` | `kubernetes.io/hostname: mr2` | pod placement |
| `tolerations` | `[]` | - | pod tolerations |
| `securityContext.runAsUser` / `runAsGroup` / `fsGroup` | `1000` / `1000` / `1000` | - | identity |
| `securityContext.supplementalGroups` | `[]` | - | extra groups (render GID added when GPU on) |
| `securityContext.readOnlyRootFilesystem` | `false` | - | Jellyfin container root fs read-only (to verify in Phase 3) |
| `gpu.enabled` | `false` | `true` | request the render node |
| `gpu.resourceName` | `devic.es/dri-render` | - | device plugin resource |
| `gpu.renderGroupId` | `992` | `992` | render GID on the GPU node |
| `gpu.vaapiDevice` | `/dev/dri/renderD128` | - | VA-API device for the Jellyfin dashboard |
| `liveTv.enabled` | `false` | `true` | render the channel list ConfigMap and mount it |
| `liveTv.mountPath` | `/livetv` | - | mount path; Jellyfin M3U tuner file `/livetv/channels.m3u` |
| `liveTv.channels` | `[]` | 11 channels | `id` (tvg-id), `name`, `group`, `url` (HLS) |
| `service.type` / `port` | `LoadBalancer` / `8096` | - | Service |
| `service.loadBalancerIP` | `""` | `192.168.0.5` | MetalLB IP (annotation `metallb.io/loadBalancerIPs`) |
| `service.addressPool` | `""` | `first-pool` | MetalLB pool (annotation `metallb.io/address-pool`) |
| `service.externalTrafficPolicy` | `Local` | - | keep client IP |
| `service.loadBalancerSourceRanges` | `[]` | `[192.168.0.0/24]` | allowed client CIDRs |
| `service.annotations` | `{}` | - | extra Service annotations |
| `networkPolicy.enabled` | `true` | - | ingress policy |
| `networkPolicy.lanCidrs` | `[]` | `[192.168.0.0/24]` | clients allowed on 8096 |
| `networkPolicy.monitoringNamespace` | `monitoring` | - | Prometheus namespace |
| `persistence.config.localPath` / `node` / `size` | `/var/lib/mr-jellyfin/config` / `""` / `20Gi` | node `mr2` | config + database volume |
| `persistence.cache.localPath` / `node` / `size` | `/var/lib/mr-jellyfin/cache` / `""` / `50Gi` | node `mr2` | cache volume |
| `persistence.media.server` / `path` | `""` / `""` | `riemerkNASS.local` / `/volumeUSB1/usbshare/media` | NAS NFS host name and export (required) |
| `persistence.media.size` / `readOnly` | `500Gi` / `true` | `458Gi` / - | media PV |
| `persistence.media.mountOptions` | `nfsvers=4.1, hard, timeo=600, retrans=3, noatime` | - | NFS mount options |
| `persistence.backup.server` / `path` | `""` / `""` | `mr0.local` / `/srv/nfs4/homes/mr/jellyfin/backup` | backup NFS target |
| `persistence.backup.size` / `mountOptions` | `50Gi` / `nfsvers=4.1, hard, timeo=600, retrans=3` | - | backup PV |
| `persistence.transcode.sizeLimit` | `30Gi` | - | `/transcode` emptyDir |
| `persistence.tmp.sizeLimit` | `2Gi` | - | `/tmp` emptyDir |
| `preflight.enabled` | `true` | - | init container |
| `preflight.libraries` | `movies, series, documentaries, home-videos` | + `music` | required folders below `/media` |
| `preflight.seedEnableMetrics` | `true` | - | first boot: `system.xml` with `EnableMetrics=true` |
| `preflight.seedTranscodePath` | `true` | - | first boot: `encoding.xml` with `TranscodingTempPath=/transcode` |
| `metrics.scrape` | `true` | - | `prometheus.io/*` pod annotations (8096 `/metrics`, or 9594 with exporter) |
| `exporter.enabled` | `false` | - | jellyfin_exporter sidecar (Phase 6) |
| `exporter.image.*` / `port` | see Images / `9594` | - | exporter |
| `exporter.apiKeySecret` / `apiKeySecretKey` | `mr-do-jellyfin-api-key` / `api-key` | - | exporter token Secret |
| `exporter.resources` | 10m/32Mi request, 100m/64Mi limit | - | exporter resources |
| `backup.enabled` | `true` | - | backup CronJob + backup PV/PVC |
| `backup.schedule` | `15 3 * * *` | - | cron (in `timeZone`) |
| `backup.keep` | `14` | - | archives kept per kind on the backup target |
| `backup.keepLocalApiArchives` | `3` | - | API archives kept in `/config/data/backups` |
| `backup.image.*` | see Images | - | backup / restore image |
| `backup.apiKeySecret` / `apiKeySecretKey` | `mr-do-jellyfin-api-key` / `api-key` | - | optional API key for `POST /Backup/Create` |
| `backup.activeDeadlineSeconds` | `3600` | - | job timeout |
| `backup.resources` | 50m/128Mi request, 1 CPU/512Mi limit | - | job resources |
| `resources` | 1 CPU / 2Gi request, 6 CPU / 8Gi limit | - | Jellyfin container (tuned in Phase 6) |
| `probes.startup` | period 10s, failure 60, timeout 5s | - | up to 10 min for start/migrations |
| `probes.liveness` | period 30s, failure 5, timeout 5s | - | `/health` |
| `probes.readiness` | period 10s, failure 3, timeout 5s | - | `/health` |
| `extraEnv` | `[]` | - | extra env for Jellyfin |

Deployment strategy is `Recreate` with `replicas: 1` (SQLite database; never two instances).

## Validation

```console
scripts/validate.sh            # static checks, no cluster access
STRICT=1 scripts/validate.sh   # also requires complete production values (before deploying)
```

Requires `helm`, `kubeconform`, Python with PyYAML; optional `promtool`, `shellcheck`, `yamllint`.
CI runs the same script (`.github/workflows/validate.yml`) with pinned, checksum-verified tools.

## Documentation

[Architecture](docs/architecture.md) - [Installation](docs/installation.md) - [Operations](docs/operations.md) -
[Troubleshooting](docs/troubleshooting.md) - [Backup and recovery](docs/backup-recovery.md) -
[Hardware compatibility](docs/hardware-compatibility.md) - [Plugins and sources](docs/plugins-and-sources.md) -
[Decisions](docs/decisions.md) - [Phase log](docs/phase-log.md)
