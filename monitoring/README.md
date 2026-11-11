# Monitoring

Integrates with the existing Prometheus v3.13.1 and Grafana 13.1.0 (namespace `monitoring`,
repository ElTabaco/mr-do-observer). No second Prometheus/Grafana, no Prometheus Operator
(a ServiceMonitor would be ignored, so none is shipped).

## Scraping (active as soon as Jellyfin runs)

The pod carries `prometheus.io/scrape: "true"`, `prometheus.io/port`, `prometheus.io/path`; the
existing `kubernetes-pods` job scrapes it and adds `namespace`, `pod`, `app` labels.

| Target | Port / path | Content |
|---|---|---|
| Jellyfin built-in | 8096 `/metrics` | .NET runtime / HTTP server metrics (`EnableMetrics`, seeded on first boot) |
| jellyfin_exporter (Phase 6, `exporter.enabled`) | 9594 `/metrics` | sessions, libraries, playback via the Jellyfin API |
| cAdvisor (existing job) | - | CPU, memory, throttling, network of the pod |
| kube-state-metrics (existing) | - | deployment, restarts, PVC phase, backup job status |

With the exporter enabled the annotation points to 9594 (one port per pod in this scrape job).

## Files

- `alerts.yaml` — Prometheus rules using only metrics available today; `alerts.test.yaml` — promtool
  unit tests (`promtool test rules alerts.test.yaml`, run by `scripts/validate.sh`).

## Phase 6 (done 2026-11-11)

Source of truth for dashboards and alerts: **ElTabaco/mr-do-observer**,
`scripts/gen-jellyfin-monitoring.py` (generates `kubernetes/grafana/alerting-configmap.yml` and
`dashboard-jellyfin-configmap.yml`). `alerts.yaml` here stays as the promtool-tested
Prometheus-format reference; the cluster Prometheus has no `rule_files` and no Alertmanager.

- **Exporter**: jellyfin_exporter v1.6.0 sidecar, collectors media, playing, system, users +
  `transcoding`, `tasks`, `storage` (`exporter.extraCollectors`). Main metrics: `jellyfin_up`,
  `jellyfin_now_playing_state`, `jellyfin_transcoding_sessions`, `jellyfin_transcoding_session_info`
  (codec, `hardware_acceleration`, method), `jellyfin_storage_free_bytes` / `_used_bytes` (library =
  NAS, program_data, cache, transcodes), `jellyfin_media_count`, `jellyfin_scrape_collector_success`.
- **Dashboard** Grafana > Media > Jellyfin (uid `mr-jellyfin`).
- **Alerts** (Grafana-managed, folder Jellyfin, group mr-jellyfin, evaluated every 1 min, repeat 12 h):
  JellyfinDown, JellyfinNotAvailable, JellyfinRestarting, JellyfinPVCNotBound,
  JellyfinMediaStorageUnreadable (NAS/NFS), JellyfinMediaStorageLow, JellyfinLocalStorageLow,
  JellyfinMemoryHigh, JellyfinCPUThrottled, JellyfinBackupFailed, JellyfinBackupMissing,
  JellyfinGuideGrabberDown, JellyfinGPUDevicePluginDown.
- **Delivery**: contact point `callmebot` (webhook) -> `callmebot-relay` (monitoring namespace,
  stdlib Python) -> CallMeBot. Rules use rule-level routing; the notification policy tree is not
  touched. Recipient (owner decision 2026-11-11): Konstantin via WhatsApp; test message delivered (HTTP 200).
  Targets live in Secret `monitoring/callmebot-relay` (key `urls`, one URL template per line with
  `{text}`), created out of band. End-to-end test 2026-11-11: a deliberately failing Job
  `mr-do-jellyfin-backup-alerttest` fired JellyfinBackupFailed after ~1.5 min (CallMeBot HTTP 200),
  deleting it sent the RESOLVED message 5 min later.
- **GPU**: the VCN video engine load is not exported continuously (`gpu_busy_percent` covers only the
  graphics engine). Measured with `scripts/loadtest/sampler.sh` (amdgpu fdinfo `drm-engine-enc`).
