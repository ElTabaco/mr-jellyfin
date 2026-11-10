# Operations

## Daily

- Health: `scripts/healthcheck.sh` (any LAN host) or `WITH_KUBECTL=1 scripts/healthcheck.sh` (mr0).
- Logs: `kubectl -n mr-do-jellyfin logs deploy/mr-do-jellyfin -c jellyfin` and the server log files
  in `/config/log/` (on mr2: `/var/lib/mr-jellyfin/config/log/`).
- Backups: run daily at 03:15 (Europe/Zurich), see [backup-recovery.md](backup-recovery.md).

## Users and permissions

- One administrator account, used only for administration. Strong password, stored in the
  password manager, never in Git.
- One normal account per person, no admin rights; enable "allow media playback" and the
  transcoding permissions per user; parental ratings per user if needed.
- Networking: keep Jellyfin's default LAN network list (private ranges). Remote access is already
  blocked at the network boundary (LAN-only LoadBalancer, no port forwarding).

## API key Secret

Needed by the backup job (API archive) and the exporter (Phase 6). Create once, after setup:

1. Dashboard > API Keys > `+`, name `mr-do-jellyfin-automation`.
2. On mr0, without the key in argv, the shell history or a file (the key is read from stdin):

```console
read -r -s -p "API key: " K && echo
printf '%s' "$K" | kubectl -n mr-do-jellyfin create secret generic mr-do-jellyfin-api-key \
  --from-file=api-key=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
unset K
```

The production Secret was created 2026-11-10 this way, fed from the Hermes secret store
(`JELLYFIN_API_KEY`) over the SSH channel's stdin. API clients must send the key in the
`Authorization: MediaBrowser Token="<key>"` header: Jellyfin 12 disables legacy authorization, and
the `api_key` query parameter is rejected for HLS endpoints (HTTP 401).

Rotate: create a new key, `kubectl -n mr-do-jellyfin delete secret mr-do-jellyfin-api-key`, create it
again, delete the old key in the dashboard. The Secret is not managed by Argo CD (no secret in Git);
it survives app syncs. Its recovery after a total loss: create a new key (above).

## Upgrade Jellyfin

1. Read the release notes (database migrations, plugin ABI changes, removed APIs).
2. Check installed plugins for the new `targetAbi` ([plugins-and-sources.md](plugins-and-sources.md)).
3. Backup: `scripts/backup.sh` (must print `BACKUP OK`).
4. PR: change `image.tag` + `image.digest` (digest of the multi-arch index) and `Chart.yaml`
   `appVersion`/`version`. `scripts/validate.sh` must pass.
5. Merge. Argo CD syncs; `Recreate` stops the old pod first. Watch
   `kubectl -n mr-do-jellyfin get pods -w` and the startup log (migrations).
6. `scripts/healthcheck.sh`, play one title, check the dashboard for errors.

Digest lookup:

```console
curl -fsSI -H "Accept: application/vnd.oci.image.index.v1+json" \
  -H "Authorization: Bearer $(curl -fsS 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:jellyfin/jellyfin:pull' | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')" \
  https://registry-1.docker.io/v2/jellyfin/jellyfin/manifests/<tag> | grep -i docker-content-digest
```

## Rollback

- Chart/config change without a database migration: revert the commit (PR), Argo CD syncs.
- Image upgrade with a database migration: **reverting the image does not revert the database.**
  Revert the image commit **and** restore the pre-upgrade backup (files backup or API archive)
  with `scripts/restore.sh` ([backup-recovery.md](backup-recovery.md)). Jellyfin 12.0 notes state
  that its database changes prevent a rollback without a full restore.

## Change Argo CD behaviour temporarily

Self-heal reverts manual `kubectl scale/patch`. For maintenance:

```console
kubectl -n argocd patch application mr-do-jellyfin --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
# ... maintenance ...
kubectl -n argocd patch application mr-do-jellyfin --type merge -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
```

`scripts/restore.sh --files` does this automatically.
