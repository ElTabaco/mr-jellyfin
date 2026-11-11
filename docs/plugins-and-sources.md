# Online sources and plugins

Status: Phase 5 (2026-11-11): plugins evaluated, Playback Reporting installed, 11 live TV channels
tested and configured. Results below; tests were run from the home connection in Switzerland.

## Phase 5 results

### Plugins (official repository, checked 2026-11-11 against Jellyfin 12.4.0)

36 plugins in the manifest; 32 have a version with `targetAbi` 12.0-12.4 (AniSearch, Bookshelf, Folio:
10.x only, not installable). Bundled and active: TMDb, OMDb, MusicBrainz, AudioDB, ListenBrainz,
Studio Images (12.4.0.0).

| Plugin | Version / ABI | Decision |
|---|---|---|
| Playback Reporting | 19.0.0.0 / 12.0.0.0 | **installed** (owner choice): playback statistics, used in Phase 6 |
| Fanart, Open Subtitles, AniList | 15 / 25 / 15, ABI 12.x | offered, not chosen (Open Subtitles needs an opensubtitles.com account) |
| TheTVDB, TVmaze, AniDB, Kitsu | ABI 12.x | not needed: TMDb matches the library |
| TVHeadend, NextPVR | ABI 12.x | only with tuner hardware/backend; none present |
| DLNA | 14.0.0.0 / 12.1.0.0 | not usable: SSDP discovery needs multicast on the LAN, the pod is on the cluster network |
| LDAP, Webhook, Session Cleaner, Transcode Killer, Reports, Trakt, Simkl, books/music extras | ABI 12.x | not needed now |

No channel plugin for a remote catalogue exists in the official repository; no custom plugin is
needed for the chosen sources (the built-in M3U tuner covers them).

### Live TV (built-in M3U tuner, channels in `values-production.yaml`)

Rule applied: only streams on the broadcaster's own CDN, no token, no DRM, no re-broadcaster, and
reachable from this connection without circumvention (no VPN/proxy). Test per channel: master
playlist -> highest variant -> newest segment (`scripts/check-livetv.py`), 2026-11-11 from mr0.

| Channel | Source host | Result | Configured |
|---|---|---|---|
| Das Erste (international feed) | daserste-live.ard-mcdn.de | OK 1080p | yes |
| 3sat (DACH feed) | zdf-hls-18.akamaized.net | OK 720p | yes |
| tagesschau24 | tagesschau.akamaized.net | OK 720p | yes |
| ARD alpha | mcdn.br.de | OK 1080p | yes |
| KiKA (worldwide feed) | kikahls.akamaized.net | OK 1080p | yes |
| BR Fernsehen Süd | mcdn.br.de | OK 1080p | yes |
| WDR Fernsehen | wdr-live.ard-mcdn.de | OK 1080p | yes |
| NDR Fernsehen Hamburg | mcdn.ndr.de | OK 1080p | yes |
| hr-fernsehen | hrhls.akamaized.net | OK 720p | yes |
| SR Fernsehen (Saarland, not Swiss SRF) | srfs.akamaized.net | OK 720p | yes |
| ORF III | orf3.mdn.ors.at | OK | yes |
| ZDF, ZDFneo, ZDFinfo, phoenix, arte (de) | ZDF/arte CDN | 403: Germany only | no |
| SWR, MDR, rbb | own CDN | 403: Germany only | no |
| ORF 2 | ors.at | 403: Austria only | no |
| ORF 1 | `test02.mdn.ors.at` (test host) | answers, but a test endpoint | no |
| RTL, VOX, ProSieben, SAT.1, kabel eins | only re-broadcasters (antik.sk, hopslan, raw IPs) | no own free stream | **no (unlicensed)** |
| SRF 1, SRF zwei, SRF info, RTS, RSI | srgssr Akamai | needs a per-session token from Play SRF | no (needs an ISP IPTV offer, e.g. Init7 TV7, or a DVB-C tuner) |
| Swiss regional (Canal 9, Canal Alpha, Léman Bleu, Rhône TV, Carac 1-5, Max TV, TeleTicino, Meteonews, Radio 3i) | own Infomaniak/CDN accounts | OK (15 streams) | not chosen by the owner |
| TeleZüri, Tele M1, TVM3, RTS Info, Couleur 3 | Kaltura/Akamai | 502/404/403 | no |

Geo-blocking is decided per programme by the broadcasters: a channel that works now can show a
"not available in your country" slate for single programmes (sports, films).

Feed choice: from Switzerland the ARD "de" playlists redirect to the international ("int") feeds;
the chart uses the int feeds directly and the highest-quality variant playlist where its name is
stable. With a master playlist Jellyfin's ffmpeg started with the first (lowest) variant: Das Erste
and KiKA arrived as 640x360 with 17-22 s until the first segment (test 2026-11-11, remux, 0 errors).

Programme guide (owner decision 2026-11-11: self-hosted): iptv-org/epg grabber (Unlicense, active,
image `ghcr.io/iptv-org/epg:master` pinned by digest) as Deployment `mr-do-jellyfin-epg`, daily at
04:30, 3 days, source teleboy.ch listings for all 11 channels; served in-cluster at
`http://mr-do-jellyfin-epg:3000/guide.xml` (NetworkPolicy: only the Jellyfin pod). Test run as uid
1000 under Pod Security restricted: 11 channels, 1350 programmes in 1 s after loading the channel
database; needs about 400 MB Node.js heap (OOM at a 768Mi limit, so 2Gi limit / 1536 MB heap).
Jellyfin 12.4's XMLTV reader throws on the empty `<star-rating system="IMDb"/>` elements in the
teleboy.ch listings (all 678 ratings of the first guide were empty) and then imports no programmes
for the channel. A sidecar in the guide pod writes `guide-clean.xml` without them every 5 minutes;
Jellyfin reads `http://mr-do-jellyfin-epg:3000/guide-clean.xml`.

Zattoo (owner request 2026-11-11): **not supported.** No M3U/IPTV/API for third-party players; access
is through Zattoo's own apps. No Jellyfin plugin exists (official repository and GitHub search); the
existing tools (Kodi pvr.zattoo, zattoo_tvh (discontinued), wakdos-streamhub) log in with the
customer account and use Zattoo's private app API - not an authorized integration. Use the Zattoo
app on the TV.

Parental control: Live TV channels have no rating, so `alexander` (unrated Live TV blocked) does
not see any channel, including KiKA.

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
