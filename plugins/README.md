# Plugins

Jellyfin plugins are installed by the administrator in the dashboard and stored in the config
volume (`/config/plugins`, settings in `/config/plugins/configurations`); they are included in the
daily files backup. This repository tracks which plugins are allowed and why.

## Policy

- Only plugins from the official repository (`https://repo.jellyfin.org/files/plugin/manifest.json`)
  or from a repository built by this project. No third-party repositories without review.
- The plugin's `targetAbi` must match the running server major/minor (12.x for Jellyfin 12.4).
- Before every Jellyfin upgrade: check each installed plugin for a compatible release; Jellyfin
  12.0 notes recommend removing non-built-in plugins before major migrations and re-adding them.
- Credentials for plugins go into Kubernetes Secrets or the plugin's own settings, never into Git.
- Only sources the owner is authorized to stream ([../docs/plugins-and-sources.md](../docs/plugins-and-sources.md)).

## Evaluation checklist (per plugin)

| Check | Record |
|---|---|
| Source repository, maintainer, last release | |
| `targetAbi` vs. server version | |
| What it needs: network access, credentials, write access | |
| Licence / terms of the content source | |
| Test: install, configure, refresh, play | |
| Rollback: uninstall, settings removed | |

## Installed plugins

None yet (Phase 5).

## Custom plugins

Built only when no built-in mechanism (M3U tuner, XMLTV, HDHomeRun, `.strm`, official plugin)
fits. A custom plugin lives in its own repository (own CI, versioning, `targetAbi`), built against
`Jellyfin.Controller`/`Jellyfin.Model` 12.4.x, and is served from a project plugin manifest.
