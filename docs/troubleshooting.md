# Troubleshooting

Commands run on mr0 unless noted.

## Pod not ready

```console
kubectl -n mr-do-jellyfin get pods -o wide
kubectl -n mr-do-jellyfin describe pod -l app=mr-do-jellyfin
kubectl -n mr-do-jellyfin logs deploy/mr-do-jellyfin -c preflight
kubectl -n mr-do-jellyfin logs deploy/mr-do-jellyfin -c jellyfin --tail=200
```

| Symptom | Cause | Fix |
|---|---|---|
| `Init:Error`, log `PREFLIGHT FAIL: /media is not an NFS mount` | media PV not mounted | check PV/PVC Bound, NAS reachable: `showmount -e <nas>` from mr2 |
| `PREFLIGHT FAIL: library folder ... does not exist` | USB volume not mounted on the NAS, or folder renamed | check the NAS; create the folder; never start without it |
| `PREFLIGHT FAIL: /config is not writable` | wrong owner of `/var/lib/mr-jellyfin/*` | on mr2: `sudo chown -R 1000:1000 /var/lib/mr-jellyfin` |
| `ContainerCreating` for minutes, event `MountVolume.SetUp failed ... nfs` | NFS server unreachable / export permission | check NAS NFS rules for 192.168.0.200/.202; `hard` mounts wait, they do not fail |
| `Pending`, event `didn't find available persistent volumes` / `node affinity` | local PV on mr2, pod forced elsewhere or mr2 down | the pod can only run on mr2 (local state); bring mr2 back |
| `Pending`, `Insufficient devic.es/dri-render` | device plugin not running, or another pod holds the GPU | `kubectl -n kube-system get pods -l app.kubernetes.io/name=generic-device-plugin -o wide` |
| `CrashLoopBackOff` after an upgrade | failed DB migration | logs; restore the pre-upgrade backup ([backup-recovery.md](backup-recovery.md)) |
| Startup probe failures during first start | migrations / first scan | allowed up to 10 min (`probes.startup`); raise `failureThreshold` if needed |
| Pod forbidden by PodSecurity | a change added root / hostPath / capabilities | fix the chart; the namespace enforces `restricted` |

## Not reachable from the LAN

- `kubectl -n mr-do-jellyfin get svc mr-do-jellyfin` -> `EXTERNAL-IP 192.168.0.5`?
  `<pending>`: IP used elsewhere or pool exhausted (`kubectl -n metallb-system logs deploy/controller`).
- With `externalTrafficPolicy: Local` only the node running the pod (mr2) announces the IP:
  `kubectl -n metallb-system logs ds/speaker | grep 192.168.0.5`.
- Client outside `192.168.0.0/24` (VPN, other VLAN): blocked by `loadBalancerSourceRanges` and the
  NetworkPolicy by design.
- `curl -v http://192.168.0.5:8096/health` from a LAN host.
- From the k3s nodes themselves (mr0, mr2) `192.168.0.5` and the ClusterIP are **not** reachable, by
  design: mr0 has no local endpoint (`externalTrafficPolicy: Local`), and node-originated traffic
  reaches the pod from the CNI bridge address (10.42.x.1), which the NetworkPolicy does not allow.
  On a node use `WITH_KUBECTL=1 SKIP_HTTP=1 scripts/healthcheck.sh` (checks `/health` inside the pod).
- One device fails, others work: capture on mr2 while the device retries
  (`tcpdump -i enp1s0 -e -nn "host <device IP> or arp"`). No `who-has 192.168.0.5` from the device =
  the request never leaves the device, so the server is not involved.

### Android Chrome: "This site can't be reached", ERR_TOO_MANY_RETRIES (2026-11-11)

Pixel 8 on the home Wi-Fi: Chrome could not open any LAN address (Jellyfin, Grafana, the router),
while the internet and the official Jellyfin app on the same phone worked. The capture showed the
phone on the LAN (DHCP, ARP for the router) but no packet from Chrome to `192.168.0.5`.
Fixed by **Settings > Apps > Chrome > Storage > Clear cache**. If it comes back, also check
Settings > Apps > Chrome > Permissions ("Nearby devices" / "Local network") and Chrome > Site
settings. The Jellyfin Android app is the better client on phones anyway (downloads, more direct play).

## Playback problems

- Dashboard > Activity and the playback log (`/config/log/FFmpeg.*.log`) show the ffmpeg command
  and the error.
- "Transcoding" although the client should Direct Play: check the client codec/container support
  and bitrate limit (user settings, client quality setting).
- VA-API errors (`Failed to initialise VAAPI`, `No VA display found`): `gpu.enabled` and the device
  plugin, then `vainfo` in the pod ([installation.md](installation.md#6-gpu-phase-4)); group 992 in
  `id` output of the container.
- Stutter with several transcodes: CPU throttling (`JellyfinCPUThrottled`), check that hardware
  encoding is active; NAS throughput (1 GbE links).

## Backup failed

`kubectl -n mr-do-jellyfin logs job/<job-name>` — the log names the failing step:
`api: FAIL` (Jellyfin API: key missing/invalid, library scan running, <5 GB free in
`/config/data/backups`), `files: FAIL` (database copy / integrity check / backup target not writable).
