# Installation

Run cluster commands on mr0 (the only host with a working kubeconfig). Host changes need the
owner's approval per phase ([phase-log.md](phase-log.md)). Values below are the production values.

## 1. NAS (Phase 2)

Synology NAS with the USB volume holding the library. Required result:

- NFS service enabled (DSM: Control Panel > File Services > NFS), NFSv4.1 enabled.
- A shared folder on the USB volume with the library folders:
  `movies/`, `series/`, `documentaries/`, `home-videos/`.
- NFS permission for the k3s nodes only: `192.168.0.200` and `192.168.0.202`, privilege
  **read-only**, squash as decided in Phase 2.
- Export path (e.g. `/volumeUSB1/usbshare/...`, confirmed in Phase 2) and the NAS host name
  go into `values-production.yaml` (`persistence.media.server`, `persistence.media.path`).

Check from mr2 (read-only test mount, removed afterwards):

```console
sudo mount -t nfs -o nfsvers=4.1,ro <nas-host>:<export> /mnt/jf-test
ls /mnt/jf-test && sudo umount /mnt/jf-test
```

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

Configure Dashboard > Playback > Transcoding with the verified codecs only
([hardware-compatibility.md](hardware-compatibility.md)).
