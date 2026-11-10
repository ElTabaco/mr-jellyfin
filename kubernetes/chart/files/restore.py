#!/usr/bin/env python3
"""Restore a files backup into the Jellyfin config volume (run by scripts/restore.sh).

Runs in a one-off pod while Jellyfin is scaled to 0. Steps:
  1. verify the archive against its .sha256 sidecar and read it completely
  2. move the current config/, plugins/, root/, data/*.db*, data/collections, data/playlists
     to /config/.pre-restore-<stamp>/ (nothing is deleted)
  3. extract the archive (tar "data" filter: no absolute paths, no links out of /config)
  4. move data-db/*.db to data/

Env: ARCHIVE = file name below /backup/files (jellyfin-files-YYYYmmdd-HHMMSS.tar.gz)
     MODE    = "files" (default) or "stage-api": copy /backup/api/ARCHIVE to /config/data/backups
"""

import datetime
import hashlib
import os
import pathlib
import shutil
import sys
import tarfile

CONFIG = pathlib.Path(os.environ.get("CONFIG_DIR", "/config"))
BACKUP = pathlib.Path(os.environ.get("BACKUP_DIR", "/backup"))
ARCHIVE = os.environ.get("ARCHIVE", "")
MODE = os.environ.get("MODE", "files")
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
RESTORED = ["config", "plugins", "root", "data/collections", "data/playlists"]


def log(msg):
    print(f"restore: {msg}", flush=True)


def verify(path):
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists():
        raise SystemExit(f"restore: FAIL checksum file {sidecar} missing")
    expected = sidecar.read_text().split()[0]
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise SystemExit(f"restore: FAIL checksum mismatch for {path}")
    log(f"checksum ok {path.name}")


def stage_api():
    source = BACKUP / "api" / ARCHIVE
    verify(source)
    target = CONFIG / "data" / "backups" / ARCHIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    log(f"staged {target}; start the restore in the Jellyfin dashboard or POST /Backup/Restore")


def restore_files():
    source = BACKUP / "files" / ARCHIVE
    if not source.is_file():
        raise SystemExit(f"restore: FAIL {source} not found")
    verify(source)
    with tarfile.open(source, "r:gz") as tar:
        names = tar.getnames()
    if "manifest.json" not in names or not any(n.startswith("data-db/") for n in names):
        raise SystemExit("restore: FAIL archive has no manifest.json or no data-db/ databases")

    keep = CONFIG / f".pre-restore-{STAMP}"
    keep.mkdir()
    moved = []
    for rel in RESTORED:
        path = CONFIG / rel
        if path.exists():
            (keep / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(keep / rel))
            moved.append(rel)
    for db_file in sorted((CONFIG / "data").glob("*.db*")):
        (keep / "data").mkdir(parents=True, exist_ok=True)
        shutil.move(str(db_file), str(keep / "data" / db_file.name))
        moved.append(f"data/{db_file.name}")
    log(f"previous state moved to {keep}: {moved}")

    with tarfile.open(source, "r:gz") as tar:
        tar.extractall(CONFIG, filter="data")
    (CONFIG / "data").mkdir(exist_ok=True)
    for db_file in sorted((CONFIG / "data-db").glob("*.db")):
        shutil.move(str(db_file), str(CONFIG / "data" / db_file.name))
        log(f"database restored: data/{db_file.name}")
    shutil.rmtree(CONFIG / "data-db")
    (CONFIG / "manifest.json").rename(keep / "restored-manifest.json")
    log(f"OK restored {ARCHIVE}")


def main():
    if not ARCHIVE or "/" in ARCHIVE:
        raise SystemExit("restore: FAIL ARCHIVE must be a plain file name")
    if MODE == "stage-api":
        stage_api()
    elif MODE == "files":
        restore_files()
    else:
        raise SystemExit(f"restore: FAIL unknown MODE {MODE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
