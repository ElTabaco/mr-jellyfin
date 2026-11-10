#!/usr/bin/env python3
"""Daily Jellyfin backup (CronJob). Standard library only.

Two independent backups per run, both written to BACKUP_DIR (NFS):

1. api/   Jellyfin's own full-system backup (POST /Backup/Create, database only).
          Needs an admin API key; skipped with a warning when the key is absent.
          The archive can be restored from the Jellyfin dashboard or by restore.sh.
2. files/ Consistent SQLite online copy (sqlite3 backup API, integrity_check) of
          data/*.db plus config/, plugins/, root/, data/collections, data/playlists.
          Works without the API and while Jellyfin is running.

Each kind keeps the newest KEEP archives. Exit code 1 if any step failed, so the
Job is marked failed and the JellyfinBackupFailed alert fires.
"""

import datetime
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

CONFIG = pathlib.Path(os.environ.get("CONFIG_DIR", "/config"))
DEST = pathlib.Path(os.environ.get("BACKUP_DIR", "/backup"))
WORK = pathlib.Path(os.environ.get("WORK_DIR", "/work"))
KEEP = int(os.environ.get("KEEP", "14"))
KEEP_LOCAL = int(os.environ.get("KEEP_LOCAL_API_ARCHIVES", "3"))
URL = os.environ.get("JELLYFIN_URL", "").rstrip("/")
API_KEY = os.environ.get("JELLYFIN_API_KEY", "").strip()
API_RETRIES = int(os.environ.get("API_RETRIES", "3"))
API_RETRY_SLEEP = int(os.environ.get("API_RETRY_SLEEP", "120"))
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

# Paths below CONFIG copied into the files archive (besides the database copies).
FILE_PATHS = ["config", "plugins", "root", "data/collections", "data/playlists"]


def log(msg):
    print(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def prune(directory, prefix, suffix, keep):
    """Keep the newest `keep` files named <prefix><stamp><suffix> (name order = age order)."""
    if keep < 1:
        log(f"retention: invalid keep={keep}, nothing deleted")
        return
    files = sorted(p for p in directory.glob(f"{prefix}*{suffix}") if p.is_file())
    for old in files[:-keep]:
        old.unlink()
        sidecar = old.with_name(old.name + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        log(f"retention: deleted {old}")


def jellyfin_request(method, path, body=None, timeout=1800):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if API_KEY:
        req.add_header("Authorization", f'MediaBrowser Token="{API_KEY}"')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"null")


def api_backup():
    """Jellyfin full-system backup (database only). Returns True on success or skip."""
    if not API_KEY:
        log("api: WARN no API key secret mounted, skipping Jellyfin API backup")
        return True
    if not URL:
        log("api: FAIL JELLYFIN_URL not set")
        return False
    options = {"Metadata": False, "Trickplay": False, "Subtitles": False, "Database": True}
    manifest = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            manifest = jellyfin_request("POST", "/Backup/Create", options)
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            detail = exc.read().decode(errors="replace")[:300] if isinstance(exc, urllib.error.HTTPError) else ""
            log(f"api: attempt {attempt}/{API_RETRIES} failed: {exc} {detail}")
            if attempt < API_RETRIES:
                time.sleep(API_RETRY_SLEEP)
    if not manifest or "Path" not in manifest:
        log("api: FAIL no backup created")
        return False

    # The server reports the archive path inside its own container; same volume here.
    source = pathlib.Path(manifest["Path"])
    if not source.is_absolute() or not source.is_relative_to(CONFIG):
        log(f"api: FAIL unexpected archive path {source}")
        return False
    with zipfile.ZipFile(source) as archive:
        if "manifest.json" not in archive.namelist() or archive.testzip() is not None:
            log(f"api: FAIL archive {source} is incomplete or corrupt")
            return False

    target_dir = DEST / "api"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    partial = target.with_name(target.name + ".part")
    shutil.copyfile(source, partial)
    if sha256(partial) != sha256(source):
        partial.unlink()
        log("api: FAIL checksum mismatch after copy")
        return False
    partial.rename(target)
    target.with_name(target.name + ".sha256").write_text(f"{sha256(target)}  {target.name}\n")
    log(f"api: OK {target} ({target.stat().st_size} bytes, server {manifest.get('ServerVersion')})")

    prune(target_dir, "jellyfin-backup-", ".zip", KEEP)
    prune(source.parent, "jellyfin-backup-", ".zip", KEEP_LOCAL)
    return True


def copy_databases(work):
    """Online, consistent copy of every SQLite database in data/."""
    results = {}
    db_dir = work / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    databases = sorted((CONFIG / "data").glob("*.db"))
    if not databases:
        raise RuntimeError(f"no SQLite databases found in {CONFIG / 'data'}")
    for db in databases:
        copy = db_dir / db.name
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
        dst = sqlite3.connect(copy)
        try:
            src.backup(dst)
            check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            dst.close()
            src.close()
        if check != "ok":
            raise RuntimeError(f"integrity_check of {db.name} copy returned {check!r}")
        results[db.name] = {"bytes": copy.stat().st_size, "integrity_check": check}
        log(f"files: database {db.name} copied, integrity ok")
    return results


def files_backup():
    work = WORK / f"files-{STAMP}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    try:
        databases = copy_databases(work)
        target_dir = DEST / "files"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"jellyfin-files-{STAMP}.tar.gz"
        partial = target.with_name(target.name + ".part")
        included = []
        with tarfile.open(partial, "w:gz") as tar:
            for rel in FILE_PATHS:
                path = CONFIG / rel
                if path.exists():
                    tar.add(path, arcname=rel)
                    included.append(rel)
            tar.add(work / "data", arcname="data-db")
            manifest = {
                "created": STAMP,
                "source": str(CONFIG),
                "included": included,
                "databases": databases,
                "restore": "see docs/backup-recovery.md (data-db/*.db -> /config/data/)",
            }
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2))
            tar.add(manifest_path, arcname="manifest.json")
        with tarfile.open(partial, "r:gz") as tar:
            tar.getmembers()  # full read: detects a truncated archive
        partial.rename(target)
        target.with_name(target.name + ".sha256").write_text(f"{sha256(target)}  {target.name}\n")
        log(f"files: OK {target} ({target.stat().st_size} bytes, included {included})")
        prune(target_dir, "jellyfin-files-", ".tar.gz", KEEP)
        return True
    except Exception as exc:  # report every failure, never swallow it
        log(f"files: FAIL {exc!r}")
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    log(f"backup start: config={CONFIG} dest={DEST} keep={KEEP}")
    if not (CONFIG / "data").is_dir():
        log(f"FAIL {CONFIG / 'data'} not found - is the config volume mounted?")
        return 1
    if not os.access(DEST, os.W_OK):
        log(f"FAIL backup target {DEST} is not writable")
        return 1
    ok_api = api_backup()
    ok_files = files_backup()
    status = "OK" if ok_api and ok_files else "FAILED"
    log(f"backup {status}: api={'ok' if ok_api else 'failed'} files={'ok' if ok_files else 'failed'}")
    return 0 if ok_api and ok_files else 1


if __name__ == "__main__":
    sys.exit(main())
