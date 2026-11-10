# Phase log

| Phase | Status | Date | Approval / result |
|---|---|---|---|
| 0 Discovery | done | 2026-11-10 | Report approved 2026-11-10 |
| 1 Repository | done, in review | 2026-11-10 | PR "Phase 1: repository, Helm chart, docs, validation"; waits for approval |
| 2 Storage | not started | | needs: Synology onboarding |
| 3 Deployment | not started | | |
| 4 AMD GPU | not started | | device plugin approved 2026-11-10 |
| 5 Online sources / plugins | not started | | |
| 6 Monitoring / four-viewer test | not started | | |
| 7 Production acceptance | not started | | |

## Owner decisions (2026-11-10)

1. Media storage: Synology NAS with a 500 GB USB device; NAS onboarding and tuning by Hermes
   (address and credentials provided on request, credentials via the secret store only).
2. mr0 backup exclude for media: approved (not needed while media stays on the NAS).
3. LoadBalancer IP `192.168.0.5`: approved.
4. Access: LAN only (no HTTPS/Ingress).
5. GPU device plugin (generic-device-plugin, mr2 only): approved.
6. Backups: like the other apps (mr0 NFS).
7. Alerts: CallMeBot.
8. Online sources: list Swiss TV and other sources -> [plugins-and-sources.md](plugins-and-sources.md);
   unlicensed sites (xStream / movie4k.to and similar) are not supported.
9. Client devices / test content: confirmed, details in Phase 6.
10. Jellyfin workload on mr2 (k3s node): approved.

## Phase 1 results

- Chart, Argo CD applications, scripts, monitoring rules, docs, CI workflows.
- `scripts/validate.sh`: PASSED (production values: one expected `PENDING(phase2)` for the NAS).
- Local functional tests of backup/restore scripts (synthetic SQLite data): passed.

## Open items

- Synology host name, NFS export path of the USB volume, NFS permissions (Phase 2).
- `readOnlyRootFilesystem` for the Jellyfin container (test in Phase 3).
- NetworkPolicy + kubelet probes on k3s (verify in Phase 3).
- Off-host copy of the backups (mr0 holds both the backups and the monthly archive).
- Prometheus `rule_files` + CallMeBot routing in mr-do-observer (Phase 6).
