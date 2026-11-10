# Phase log

| Phase | Status | Date | Approval / result |
|---|---|---|---|
| 0 Discovery | done | 2026-11-10 | Report approved 2026-11-10 |
| 1 Repository | done, in review | 2026-11-10 | PR #1; waits for merge |
| 2 Storage | done, in review | 2026-11-10 | Changes A1-A4, B-E approved 2026-11-10 ("approve all"); results below |
| 3 Deployment | not started | | needs PR #1 merged |
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
11. Phase 2 (2026-11-10): NAS `riemerkNASS` 192.168.0.233, user riemer, library `/usbmedia/media`;
    approved: library folders, series reorganisation, NFS hardening, host directories, chart values,
    storage test.

## Phase 1 results

- Chart, Argo CD applications, scripts, monitoring rules, docs, CI workflows.
- `scripts/validate.sh`: PASSED (production values: one expected `PENDING(phase2)` for the NAS).
- Local functional tests of backup/restore scripts (synthetic SQLite data): passed.

## Phase 2 results (2026-11-10)

NAS (Synology DS220+, DSM 7.3.2-86009 Update 5):
- Onboarded for Hermes (SSH key for riemer; DSM home dir mode 777 -> 755, required for key login).
- A1: created `media/series`, `media/documentaries`, `media/home-videos` (owner riemer:users).
- A2: 79 episode files moved from `movies/anime` to `series/` with Jellyfin names:
  `Hellsing (2001)` 13, `Hellsing Ultimate (2006)` 10, `Drifters (2016)` 12,
  `One Piece (1999)` 44 (absolute numbers 811-854, file names kept). `movies/anime/Drifters/Drifter.mp4`
  (unknown content) left in place. Log + undo script on the NAS:
  `media/.hermes-reorg-20261110-201310.log`, `media/.hermes-reorg-20261110-201310-undo.sh`.
- A3: NFS rule `*` rw/no_root_squash/insecure replaced by `192.168.0.202` + `192.168.0.200`
  read-only, root squash, privileged ports (DSM WebAPI). No NFS client was connected before the change.
- A4: no static IP set in DSM: the name `riemerkNASS.local` comes from the router's DHCP/DNS, and a
  static DSM address could drop that record or collide with the DHCP pool. Router reservation:
  owner action (open item).

Hosts:
- B: mr2 `/var/lib/mr-jellyfin/{config,cache}` 1000:1000 0750 (850 GB free).
- C: mr0 `/srv/nfs4/homes/mr/jellyfin/backup` 0775.

Repository (D): `values-production.yaml` media `riemerkNASS.local:/volumeUSB1/usbshare/media`, 458Gi,
libraries + `music`. `STRICT=1 scripts/validate.sh`: PASSED (31 objects valid against k8s 1.37.2).

Storage test (E), temporary namespace `mr-do-jellyfin-storagetest`, chart-rendered PVs/PVCs, pod on mr2
as uid 1000 under Pod Security `restricted`:
- All 4 PVCs Bound to their static PVs within 3 s.
- Chart preflight: `/media is nfs4`, 5 library folders ok, `preflight: OK`.
- Mounts: media `nfs4 ro,vers=4.1,hard,timeo=600,retrans=3,noatime`; backup `nfs4 rw,vers=4.1`;
  config/cache ext4 on mr2 NVMe.
- Media write attempt: `Read-only file system` (expected). Backup NFS write + delete: ok.
- Cache write 256 MiB with fsync: 327 MB/s. Media sequential read: 117 MB/s and 116 MB/s
  (1 GbE limit; NAS page cache not dropped).
- Inventory: movies 1, series 79, documentaries 0, home-videos 0, music 15,579 files.
- Recovery: pod deleted and recreated -> marker file from the first pod found on the local PV,
  NFS volumes mounted again, preflight OK.
- Cleanup: test namespace, 4 test PVs and the mr2 test directory removed; no test files left on NAS/mr0.
- Not tested: NFS access from a host outside the rule (test host mr-v100 unreachable); verified by
  the generated `/etc/exports` only. NAS outage during playback (Phase 6).

## Open items

- DHCP reservation for the NAS (192.168.0.233) on the router (owner).
- `movies/anime/Drifters/Drifter.mp4`: unknown content, owner to classify.
- One Piece absolute numbering: matching to be checked after the first library scan (Phase 3).
- Media on a single USB SSD without a copy; optional NAS-side copy to `/volume1` (RAID 1).
- `readOnlyRootFilesystem` for the Jellyfin container (test in Phase 3).
- NetworkPolicy + kubelet probes on k3s (verify in Phase 3).
- Off-host copy of the backups (mr0 holds both the backups and the monthly archive).
- Prometheus `rule_files` + CallMeBot routing in mr-do-observer (Phase 6).
