# Online sources and plugins

Status: Phase 1 inventory. Every candidate is verified individually in Phase 5 (technical test
**and** terms of use) before it is configured. Nothing here is promised to work.

## Three different things

| Term | Meaning | In Jellyfin |
|---|---|---|
| Catalogue entry | metadata about a title (name, poster, description) | library item, metadata provider plugin |
| Playable stream | a URL the server/client can play (HLS, MPEG-TS, ...) | Live TV tuner (M3U, HDHomeRun), channel plugin, `.strm` file |
| Local media file | a file on storage Jellyfin can read | library on the NAS (`/media/...`) |

A source can provide one, two or all three. A catalogue without a legal stream is not playable.

## Jellyfin extension points (verified against Jellyfin 12.4 sources / official repository)

- Plugins are .NET assemblies built against the `Jellyfin.Controller` / `Jellyfin.Model` packages
  (12.4.0 published on NuGet) with a `targetAbi`. Jellyfin 12.0 changed the database and some
  APIs; plugins must declare a 12.x ABI. The official plugin template still targets 10.11
  (checked 2026-11-10), so a custom plugin needs its SDK references updated.
- Official repository `https://repo.jellyfin.org/files/plugin/manifest.json`: 36 plugins, most with
  a 12.x ABI (Live TV: TVHeadend 12.0, NextPVR 12.1).
- Built-in Live TV: M3U tuner + XMLTV guide, HDHomeRun tuners.
- Channel plugins (`IChannel`): browsable remote catalogues with playable items.
- `.strm` files: a text file with a stream URL inside a normal library.
- Kodi add-ons (Python) and Kodi repositories **cannot** be installed in Jellyfin. Different
  runtime, different plugin API.

## Swiss TV

| Source | Kind | Status | Notes |
|---|---|---|---|
| SRG SSR live channels (SRF 1, SRF zwei, SRF info, RTS 1/2, RSI LA 1/2, RTR) | live stream | **candidate, verify** | Free on the broadcaster's Play platforms in Switzerland (geo-restricted). Check whether stream URLs may be used in third-party players and whether they are DRM-protected; only then M3U entry. |
| SRG SSR on-demand (Play SRF, Play Suisse) | on-demand | **candidate, verify** | No documented public API known; check terms and DRM. |
| Swiss ISP IPTV with an official M3U for customers (e.g. Init7 TV7) | live stream (M3U) | **candidate, only if you are a customer** | Built-in M3U tuner; verify the playlist URL and terms with the provider. |
| DVB-C cable (unencrypted channels) via a network tuner (HDHomeRun) or TVHeadend + tuner | live stream | **supported technology, needs hardware** | Jellyfin supports HDHomeRun natively; TVHeadend plugin (ABI 12.0). Channel availability depends on the cable provider. |
| Zattoo, Teleboy, blue TV (Swisscom), Sunrise TV, Salt TV | app-based IPTV | **not supported unless the provider offers M3U/IPTV for third-party players** | No documented third-party interface known; their app terms usually forbid other players. |

## Other public / free sources

| Source | Kind | Status | Notes |
|---|---|---|---|
| iptv-org lists (community index of publicly available streams) | M3U | **per channel only** | The index itself grants no rights; use only entries whose broadcaster offers the stream for free public use; verify each channel. |
| German public broadcasters (ARD/ZDF Mediathek) | on-demand | **candidate, verify** | Public offering; check terms for third-party playback or personal-use downloads to local files. |
| Your own recordings, home videos, purchased DRM-free files | local file | **supported** | Normal libraries on the NAS. |

## Not supported

| Source | Reason |
|---|---|
| Kodi xStream add-on and sites like movie4k.to, kinox, s.to, bs.to and similar | They distribute copyrighted films and series without a licence. This project only integrates content you are authorized to stream; no scrapers, plugins or `.strm` links for these sites. Also technically incompatible (Kodi Python add-ons). |
| Netflix, Disney+, Prime Video, Apple TV+, Sky/blue+ and similar subscription services | DRM (Widevine/PlayReady/FairPlay), no third-party playback API, terms forbid it. Use their own apps on the TV. |
| YouTube | Terms forbid third-party download/stream extraction. |
| Arbitrary websites | Each source is checked individually; no generic scraping. |

## Phase 5 procedure per source

1. You confirm the source and your entitlement (subscription/customer/free public offering).
2. Check terms of use and DRM; record the result here.
3. Technical test: stream format, geo-restriction, authentication, stability (24 h).
4. Configure (M3U tuner / XMLTV / official plugin / `.strm`), credentials only in a Kubernetes
   Secret, never in Git.
5. Availability monitoring (Phase 6) and catalogue/guide refresh schedule.
6. A custom plugin only if no built-in mechanism fits; it lives in a separate repository with its
   own CI and `targetAbi` 12.x, and is installed from a local plugin repository manifest.
