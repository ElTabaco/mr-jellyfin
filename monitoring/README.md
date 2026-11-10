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

## Phase 6 (needs approval, changes in mr-do-observer)

- Add `rule_files` + these rules to the Prometheus ConfigMap.
- Alert delivery to CallMeBot (Grafana alerting contact point / webhook), no new Alertmanager unless decided.
- Grafana dashboard "Jellyfin" (ConfigMap provisioned like the existing dashboards).
- GPU metrics (amdgpu sysfs: `gpu_busy_percent`, VRAM/GTT) and NAS availability: exporter choice
  after checking maintenance status; metric names verified before alerts are written.
