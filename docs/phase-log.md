# Phase log

| Phase | Status | Date | Approval / result |
|---|---|---|---|
| 0 Discovery | done | 2026-11-10 | Report approved 2026-11-10 |
| 1 Repository | done | 2026-11-10 | PR #1 merged |
| 2 Storage | done | 2026-11-10 | Changes A1-A4, B-E approved 2026-11-10 ("approve all"); results below |
| 3 Deployment | done | 2026-11-10/11 | approved 2026-11-10; owner playback test OK 2026-11-11 |
| 4 AMD GPU | done | 2026-11-11 | approved 2026-11-11; PR #3, #4 merged |
| 5 Online sources / plugins | in progress | 2026-11-11 | approved 2026-11-11; results below |
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

## Phase 3 results (2026-11-10/11)

Deployment (`kubectl apply -f kubernetes/application.yaml` on mr0, then Argo CD):
- Argo CD `mr-do-jellyfin` Synced/Healthy within 30 s; namespace with Pod Security `restricted`.
- Pod on mr2 as uid 1000, 0 restarts; 4 PVCs Bound; Service `192.168.0.5:8096` (MetalLB).
- Preflight: NFS media + 5 libraries ok; seeded `EnableMetrics=true`, `TranscodingTempPath=/transcode`.
- Jellyfin 12.4.0 started in 4.8 s, ffmpeg 8.1.3 (jellyfin-ffmpeg). No errors in the startup log
  (EF Core migration warnings on the fresh database only).
- LAN (from the Hermes host): `/health` 200, `/web/` 200, `/System/Info/Public`, `/metrics` ok.
- Probes work with the NetworkPolicy; a pod in another namespace is refused (NetworkPolicy works).
  The LB IP / ClusterIP is not reachable from the nodes themselves (by design, see troubleshooting).
- Prometheus `kubernetes-pods` job scrapes `10.42.2.19:8096/metrics`: up.

Setup (owner in the browser): wizard done, admin user `mr`, remote access off, UPnP off, metadata
country CH, API key `mr-do-jellyfin-automation` (Hermes store `JELLYFIN_API_KEY`, Kubernetes Secret
`mr-do-jellyfin-api-key`, created from stdin, 32 chars, not in Git).

Libraries (API, realtime monitoring off because NFS changes are not visible to inotify; scheduled
scan every 12 h): Movies `/media/movies`, Shows `/media/series`, Documentaries `/media/documentaries`,
Home Videos `/media/home-videos`, Music `/media/music`.

First full scan: 2 h 15 min (mostly music metadata). Result: 1 movie, 4 series, 79 episodes,
516 albums, 15,322 songs, 2,584 artists.
- Matched with TMDb/TVDb/IMDb ids, seasons and episode titles: Drifters (2016) 12/12,
  Hellsing (2001) 13/13, Hellsing Ultimate (2006) 10/10.
- One Piece (1999) matched (ids ok), but the 44 episodes (absolute numbers 811-854, no season folder)
  landed in "Season Unknown". 2026-11-11: moved to `Season 19` (TMDb numbering, S19E08-S19E51), then
  the whole series was deleted from the NAS on owner request (44 files, 6.0 GB; no recycle bin on the
  USB share). Log: `media/.hermes-onepiece-20261111-001550.log`.
- `movies/anime/Drifters/Drifter.mp4` ("Drifter (2011)", misdetected as "Drifters") deleted on owner
  request 2026-11-11; empty `movies/anime/` removed.
- Music: many files only have ID3v1 tags (warning "some fields may be truncated").

Playback (API test, Hellsing S01E01, h264 720x540 + aac in mp4):
- Direct Play supported; direct stream 52 MB at 28-29 MB/s.
- Remux HLS (stream copy) ok; forced software transcode (libx264, 640 px, 250 kbit/s): 25x realtime,
  0 ffmpeg errors. No GPU yet (Phase 4).
- Client playback (browser + Android TV): owner test 2026-11-11 - OK.

User accounts (2026-11-11, API): `schmutz`, `alexander`, `cose` - not admin, all libraries,
remote access off, no content deletion, no control of other sessions. Initial random passwords only in
the Hermes secret store (`JELLYFIN_PW_<NAME>`); users change them in the client (Settings > Profile).
`alexander`: max parental rating 12, unrated movies/shows/trailers/Live TV/channel content blocked.
Verified: with the current library (ratings TV-MA, CH-16, R) `alexander` sees no movie or series,
`schmutz` sees all. User `liudmyla` was created by the owner in the dashboard.

Backup with API key: `BACKUP OK` - API archive `jellyfin-backup-20261111000536.zip` (8.7 MB,
67 entries, manifest server 12.4.0.0, sha256 ok) + files archive (26.6 MB, integrity ok).

## Phase 4 results (2026-11-11, part 1)

- GPU state before: `/dev/dri/renderD128` root:render(992), no process using `/dev/dri`, `gpu_busy_percent` 0.
- Device plugin app `mr-do-jellyfin-gpu-device-plugin` applied (`kubectl apply -f
  kubernetes/platform/gpu-device-plugin/application.yaml`). The DaemonSet pod failed with
  `StartError`: runc could not create `/dev/termination-log` because host `/dev` is mounted read-only
  over the container's `/dev`. Fix: `terminationMessagePath: /tmp/termination-log` (this PR). Verified
  with an identical test pod: plugin registered, node allocatable `devic.es/dri-render: 1`.
- vainfo + ffmpeg tests in a non-privileged pod with the production image: see
  [hardware-compatibility.md](hardware-compatibility.md). HW decode H.264/HEVC 8+10-bit/VP9/AV1, HW
  encode H.264/HEVC/AV1; no MPEG-2/VC-1/VP8; HDR tone mapping failed (no HDR content in the library).
  Software transcode 1080p->720p used 7.9 CPU cores, the VA-API transcode 0.27 cores.
- Test namespace removed.

## Phase 4 results (2026-11-11, part 2, after PR #3 merge)

- Argo CD synced both apps to `d4e7ae4` within 30 s: device plugin pod Running (0 restarts), node mr2
  allocatable/allocated `devic.es/dri-render` 1/1, Jellyfin restarted once with the render node.
- `scripts/configure-transcoding.py` applied VA-API settings (idempotent re-run: no change).
- Jellyfin transcodes use the GPU: H.264 source fully in hardware (31.6x, 0.36 CPU cores); VP8 source
  software decode + hardware encode (28x, 6 cores = pod limit). Details in
  [hardware-compatibility.md](hardware-compatibility.md).

## Phase 5 results (2026-11-11)

- Owner: NAS DHCP reservation on the router done (NAS still 192.168.0.233, `riemerkNASS.local`).
- Owner choices: plugin Playback Reporting; live TV with German-language public channels (ARD alpha,
  KiKA, tagesschau24 + "ARD, ZDF, RTL, SRF, ORF and the most common German-language channels").
- Playback Reporting 19.0.0.0 (ABI 12.0) installed from the official repository; pod restarted
  (`kubectl delete pod`), plugin `Active`.
- 22 German/Austrian channel URLs tested; 11 configured (Git: `liveTv.channels`), the others are
  geo-blocked, token-protected or only available from re-broadcasters:
  [plugins-and-sources.md](plugins-and-sources.md).
- Chart: `liveTv` values, ConfigMap `mr-do-jellyfin-livetv` mounted at `/livetv` (read-only).
- Scripts: `configure-livetv.py` (M3U tuner + guide refresh), `check-livetv.py` (availability);
  check from mr0: 11/11 OK.
- After PR #5: Jellyfin restarted with `/livetv/channels.m3u`; `configure-livetv.py` added the M3U tuner;
  11 channels in Jellyfin. Playback through the server (HLS remux, 0 ffmpeg errors): Das Erste and
  KiKA 640x360 after 22 s / 18 s, ORF III 960x540 after 5 s -> variant playlists (PR #6).
- Owner: programme guide yes (self-hosted grabber); alexander keeps Live TV blocked; Zattoo requested
  -> not possible (no authorized interface, no plugin), see plugins-and-sources.md.
- Guide grabber tested in a temporary restricted namespace (removed): 1350 programmes for 11 channels.

## Open items

- VP8/MPEG-2/VC-1 sources decode in software at up to 6 cores; transcode throttling decision in Phase 6.
- HDR tone mapping untested with real HDR content (failed with a generated file).

- DHCP reservation for the NAS (192.168.0.233) on the router (owner).
- `movies/anime/Drifters/Drifter.mp4`: unknown content, owner to classify.
- Media on a single USB SSD without a copy; optional NAS-side copy to `/volume1` (RAID 1).
- `readOnlyRootFilesystem` for the Jellyfin container (not tested yet; stays false).
- Off-host copy of the backups (mr0 holds both the backups and the monthly archive).
- Prometheus `rule_files` + CallMeBot routing in mr-do-observer (Phase 6).
