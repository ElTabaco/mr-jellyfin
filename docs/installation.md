# Installation

Run cluster commands on mr0 (the only host with a working kubeconfig). Host changes need the
owner's approval per phase ([phase-log.md](phase-log.md)). Values below are the production values.

## 1. NAS (Phase 2, done 2026-11-10)

Synology DS220+ `riemerkNASS` (192.168.0.233, DHCP), DSM 7.3.2. Library on the USB SSD
(WD Red SA500 500 GB, ext4), DSM share `usbmedia` = `/volumeUSB1/usbshare`:

```text
/volumeUSB1/usbshare/media/
  movies/          series/          documentaries/     home-videos/     music/     games/ (not a library)
  series/<Series Name (year)>/Season 01/<Series Name (year)> S01E01.mp4
```

- NFS service on, NFSv4 on, minor version 1 (4.2 is not offered by DSM 7.3).
- NFS permissions of share `usbmedia` (DSM: Control Panel > Shared Folder > usbmedia > NFS Permissions),
  set through the DSM WebAPI `SYNO.Core.FileServ.NFS.SharePrivilege` (same as the UI):
  `192.168.0.202` and `192.168.0.200`, read-only, "Map root to guest", privileged ports only,
  async, cross-mount. Resulting export:
  `/volumeUSB1/usbshare 192.168.0.202(ro,root_squash,secure,...) 192.168.0.200(ro,root_squash,secure,...)`.
- Files are owned by uid 1026 (riemer) with mode 777/755 dirs: readable by the Jellyfin uid 1000.
- Recommended: DHCP reservation for 192.168.0.233 on the router. The chart uses the name
  `riemerkNASS.local` (router DNS), which follows the DHCP lease.

Check from mr2 (read-only test mount, removed afterwards):

```console
sudo mount -t nfs -o nfsvers=4.1,ro riemerkNASS.local:/volumeUSB1/usbshare/media /mnt/jf-test
ls /mnt/jf-test && sudo umount /mnt/jf-test
```

Adding media: copy files into the library folders on the NAS (SMB/File Station), using the
Jellyfin naming above; Jellyfin picks them up with its library scan.

## 2. Node directories on mr2 (Phase 2)

```console
sudo install -d -o 1000 -g 1000 -m 0750 /var/lib/mr-jellyfin /var/lib/mr-jellyfin/config /var/lib/mr-jellyfin/cache
```

## 3. Backup directory on mr0 (Phase 2)

```console
sudo install -d -m 0775 /srv/nfs4/homes/mr/jellyfin /srv/nfs4/homes/mr/jellyfin/backup
```

The mr0 export squashes all clients to UID 0 (`all_squash,anonuid=0`), so the backup job can write.

## 4. Validate

```console
STRICT=1 scripts/validate.sh
```

Must pass: no `PENDING` values left.

## 5. Deploy (Phase 3)

```console
git clone https://github.com/ElTabaco/mr-jellyfin.git && cd mr-jellyfin
kubernetes/apply.sh
kubectl -n mr-do-jellyfin get pods -w
scripts/healthcheck.sh
```

Then in the browser `http://192.168.0.5:8096`: run the setup wizard, create the admin account
(strong password, stored in the password manager), create libraries
`/media/movies` (Movies), `/media/series` (Shows), `/media/documentaries`, `/media/home-videos`.

After setup: create the API key Secret ([operations.md](operations.md#api-key-secret)).

## 6. GPU (Phase 4)

```console
kubernetes/apply.sh --gpu
kubectl get node mr2 -o jsonpath='{.status.allocatable}'   # devic.es/dri-render: "1"
```

Set `gpu.enabled: true` in `values-production.yaml` (PR), then verify inside the pod:

```console
kubectl -n mr-do-jellyfin exec deploy/mr-do-jellyfin -- /usr/lib/jellyfin-ffmpeg/vainfo --display drm --device /dev/dri/renderD128
```

Then apply the verified Jellyfin transcoding settings (VA-API, hardware decode H.264/HEVC/VP9/AV1,
hardware encoding, no tone mapping) from a LAN host, key from stdin:

```console
python3 /opt/data/bin/hermes_secrets.py get JELLYFIN_API_KEY | scripts/configure-transcoding.py
```

Results and the codec matrix: [hardware-compatibility.md](hardware-compatibility.md).

Configure Dashboard > Playback > Transcoding with the verified codecs only
([hardware-compatibility.md](hardware-compatibility.md)).

## 7. Plugins and live TV (Phase 5)

Plugins come only from the official repository (`https://repo.jellyfin.org/files/plugin/manifest.json`,
checked for a 12.x `targetAbi`); install in Dashboard > Plugins > Catalog or through the API, then
restart the pod (`kubectl -n mr-do-jellyfin delete pod -l app=mr-do-jellyfin`). Plugin files live in
`/config/plugins` (persistent, included in the backup). Installed: Playback Reporting 19.0.0.0.

Live TV channels are Git-managed in `values-production.yaml` (`liveTv.channels`). After the first
deploy, register the tuner once from a LAN host, then check the streams:

```console
python3 /opt/data/bin/hermes_secrets.py get JELLYFIN_API_KEY | scripts/configure-livetv.py
scripts/check-livetv.py      # on a LAN host (geo-restriction depends on the connection)
```

Adding a channel: test it with `scripts/check-livetv.py --m3u <file>`, check the source rules in
[plugins-and-sources.md](plugins-and-sources.md), add it to `liveTv.channels` (PR), wait ~1 min after
the Argo CD sync and run the guide refresh (Dashboard > Live TV > Refresh guide data).
