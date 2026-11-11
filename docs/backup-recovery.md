# Backup and recovery

## What is backed up

| Data | Where it lives | Backup |
|---|---|---|
| Database (users, settings, watch state, library index) | `/config/data/*.db` (mr2 local) | daily, two methods (below) |
| Server configuration | `/config/config/*.xml` | daily files backup |
| Plugins + plugin configuration | `/config/plugins/`, `/config/plugins/configurations/` | daily files backup |
| Library definitions, collections, playlists | `/config/root/`, `/config/data/collections`, `/config/data/playlists` | daily files backup |
| Metadata images / cache | `/config/metadata`, `/cache` | not backed up (rebuilt by a library scan) |
| Media | Synology NAS | not part of this project (NAS-side backup) |
| Deployment values | Git (this repository) | GitHub |
| Secret `mr-do-jellyfin-api-key` | Kubernetes only | not backed up: recreate ([operations.md](operations.md#api-key-secret)) |
| Argo CD Application | Git (`kubernetes/application.yaml`) | `kubernetes/apply.sh` |

## Methods (CronJob `mr-do-jellyfin-backup`, daily 03:15 Europe/Zurich)

1. **API archive** (`/backup/api/jellyfin-backup-<stamp>.zip`): Jellyfin's built-in full-system
   backup (`POST /Backup/Create`, database only). Jellyfin optimizes the database and reads it
   in a transaction. Needs the API key Secret; without it this step is skipped with a warning.
   Refused by Jellyfin while a library scan runs (the job retries 3x, 2 min apart).
2. **Files archive** (`/backup/files/jellyfin-files-<stamp>.tar.gz`): SQLite online backup
   (consistent snapshot while Jellyfin runs) of every `data/*.db`, `PRAGMA integrity_check` on the
   copy, plus the config/plugins/library-definition folders and a `manifest.json`.

Every archive gets a `.sha256` sidecar. Archives are written as `.part` and renamed when complete.
Retention: newest 14 of each kind (`backup.keep`), API archives inside `/config/data/backups`: 3.
Any failed step fails the Job -> alert `JellyfinBackupFailed`; no success for 26 h -> `JellyfinBackupMissing`.

Target: `mr0.local:/srv/nfs4/homes/mr/jellyfin/backup` (like the other mr-do-* apps). mr0's
monthly `backup.timer` archives `/srv/nfs4` to `/home/mr/backup` (6 kept), so the Jellyfin backups
are also in those monthly archives. Both copies are on mr0's disk: off-host copy is an open item.

## Backup before an upgrade

```console
scripts/backup.sh     # creates a Job from the CronJob, waits, prints the log, exit 1 on failure
```

## Restore

List:

```console
scripts/restore.sh --list
```

Files archive (Jellyfin stopped during the restore):

```console
scripts/restore.sh --files jellyfin-files-YYYYmmdd-HHMMSS.tar.gz
```

The script asks for `RESTORE`, suspends Argo CD auto-sync, scales Jellyfin to 0, runs a restore pod
(checksum check, current state moved to `/config/.pre-restore-<stamp>/`, extract, databases to
`data/`), scales back to 1, re-enables auto-sync (also on failure). Nothing is deleted; remove
`.pre-restore-*` manually once the restore is verified.

API archive (Jellyfin's own restore):

```console
scripts/restore.sh --stage-api jellyfin-backup-YYYYmmddHHMMSS.zip
```

Then Dashboard > Backups > restore that archive (or `POST /Backup/Restore` with
`{"ArchiveFileName": "<name>"}`); Jellyfin restarts and applies it.

After any restore: log in, check users, libraries, watch state; run a library scan
(Jellyfin 12.0 notes require a full scan after a migration).

## Rollback after a failed upgrade

The image tag can be reverted in Git, but **the database stays migrated**. Order:

1. Revert the image commit (PR, merge) — or keep Argo CD suspended.
2. `scripts/restore.sh --files <pre-upgrade archive>` (or stage + restore the pre-upgrade API archive).
3. Verify. Old server version + restored pre-upgrade database = consistent state.

## Disaster recovery (mr2 lost)

1. Reinstall the node, join k3s as `mr2`, recreate `/var/lib/mr-jellyfin/{config,cache}` (1000:1000).
2. The Argo CD app recreates everything except the Secret; the pod starts with an empty config.
   Suspend auto-sync, scale to 0, restore the newest files archive, scale to 1, re-enable.
3. Recreate the API key Secret. Restore GPU: device plugin app.

## Restore test

Tested locally (Phase 1, sandbox, synthetic data): backup -> modify database -> restore -> data
back; corrupt archive rejected by checksum; missing database fails the backup.

Cluster test with real data (Phase 7, 2026-11-11): the scheduled archive
`jellyfin-files-20261111-031500.tar.gz` was restored with `files/restore.py` into an isolated
instance (temporary namespace, backup volume mounted read-only, emptyDir config, same Jellyfin
image). Users, libraries, plugins, transcoding and live TV settings and item counts were identical to
production; production was not touched. Details in [phase-log.md](phase-log.md).

A Jellyfin instance started from a restored `/config` needs a writable `/transcode` (set in
`encoding.xml`); without it Jellyfin stops at startup with `Access to the path '/transcode' is denied`.
The chart provides it; mount an emptyDir there in any manual recovery instance.
