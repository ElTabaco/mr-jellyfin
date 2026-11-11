# Hardware compatibility report

Status: **Phase 4 measured (2026-11-11).** Hardware transcoding is configured only for codecs that
`vainfo` and real ffmpeg runs confirmed.

## Measured (Phase 0, 2026-11-10, read-only)

| Item | Value | Source |
|---|---|---|
| Node | mr2 (192.168.0.202), Ubuntu 24.04.5, kernel 7.0.0-42-generic | `kubectl get nodes -o wide` |
| CPU | AMD Ryzen 7 7840HS, 8 cores / 16 threads | `lscpu` |
| GPU | AMD Phoenix1 `[1002:15bf]` rev c2 (Radeon 780M, RDNA3) at `c5:00.0` | `lspci -nn` |
| Driver | `amdgpu` loaded | `lsmod` |
| Video engine | VCN 4.0 (`vcn_v4_0_0`), firmware "ENC: 1.19 DEC: 7", VCN fw `0x07113000` | `dmesg`, `amdgpu_firmware_info` |
| Devices | `/dev/dri/card0` root:video (44), `/dev/dri/renderD128` root:render (992), `/dev/kfd` root:render | `ls -l /dev/dri /dev/kfd` |
| Memory | UMA carve-out 512 MiB (`mem_info_vram_total`), GTT 16 GiB | sysfs |
| Load | `gpu_busy_percent` 0; no pod uses `/dev/dri`; no privileged pods; no device plugin; no CDI | sysfs, pod specs |
| cgroup | v2 | `stat -fc %T /sys/fs/cgroup` |
| Host tools | no `vainfo`, no `ffmpeg` on the host (not installed by design) | `command -v` |
| mr0 GPU | Intel Haswell HD 4600 `[8086:0412]` — not used | `lspci` |

## Measured (Phase 4, 2026-11-11)

Test: temporary namespace `mr-do-jellyfin-gputest` on mr2, pod with the production Jellyfin image
(jellyfin-ffmpeg 8.1.3, Mesa 26.0.8 radeonsi), uid 1000, supplemental group 992, no privileged mode,
`/dev/dri/renderD128` from the device plugin (`devic.es/dri-render: 1`). Sources generated in the pod
with software encoders (testsrc2 pattern; real content can compress differently). Scripts and logs:
Hermes scratch `gputest/`. Namespace removed after the test.

### vainfo (verbatim)

```text
vainfo: Driver version: Mesa Gallium driver 26.0.8 for AMD Radeon 780M Graphics (radeonsi, phoenix, ACO, DRM 3.64, 7.0.0-42-generic)
VAProfileH264ConstrainedBaseline: VAEntrypointVLD / VAEntrypointEncSlice
VAProfileH264Main               : VAEntrypointVLD / VAEntrypointEncSlice
VAProfileH264High               : VAEntrypointVLD / VAEntrypointEncSlice
VAProfileHEVCMain               : VAEntrypointVLD / VAEntrypointEncSlice
VAProfileHEVCMain10             : VAEntrypointVLD / VAEntrypointEncSlice
VAProfileJPEGBaseline           : VAEntrypointVLD
VAProfileVP9Profile0            : VAEntrypointVLD
VAProfileVP9Profile2            : VAEntrypointVLD
VAProfileAV1Profile0            : VAEntrypointVLD / VAEntrypointEncSlice
VAProfileNone                   : VAEntrypointVideoProc
```

### Codec matrix

| Codec | HW decode | HW encode | Evidence |
|---|---|---|---|
| H.264 8-bit | yes | yes (`h264_vaapi`) | vainfo + ffmpeg |
| HEVC 8-bit | yes | yes (`hevc_vaapi`) | vainfo + ffmpeg |
| HEVC 10-bit (Main10) | yes | yes (`hevc_vaapi -profile:v main10`) | vainfo + ffmpeg |
| VP9 profile 0 | yes | no | vainfo + ffmpeg |
| VP9 profile 2 (10-bit) | vainfo only | no | not run |
| AV1 8/10-bit (Profile0) | yes | yes (`av1_vaapi`) | vainfo + ffmpeg (8-bit) |
| MPEG-2 | **no** | no | not in vainfo; ffmpeg fell back to software (6.5 CPU cores) |
| VC-1, VP8 | **no** | no | not in vainfo |
| HDR10 -> SDR tone mapping | **failed** | - | see below |

### Performance (single run each, `-benchmark`, CPU = (utime+stime)/rtime)

| Test | fps | CPU cores | `gpu_busy_percent` |
|---|---|---|---|
| decode H.264 1080p | 1268 | 0.39 | 0 % |
| decode HEVC 8-bit 1080p | 962 | 0.33 | <=1 % |
| decode HEVC 10-bit 2160p | 258 | 0.23 | <=1 % |
| decode AV1 1080p | 1089 | 0.25 | <=1 % |
| decode VP9 1080p | ~930 (300 frames in 0.32 s) | 0.3 | - |
| software decode HEVC 10-bit 2160p (reference) | 214 | 7.54 | - |
| H.264 1080p -> `h264_vaapi` 720p 3 Mbit/s | 490 | 0.27 | avg 8 %, max 12 % |
| H.264 1080p -> `hevc_vaapi` 1080p 4 Mbit/s | 437 | 0.24 | max 12 % |
| H.264 1080p -> `av1_vaapi` 1080p 3 Mbit/s | 453 | 0.24 | <=1 % |
| HEVC 10-bit 2160p -> `h264_vaapi` 1080p 8 Mbit/s | 156 | 0.26 | avg 13 %, max 18 % |
| HEVC 10-bit 2160p -> `hevc_vaapi` Main10 2160p | 109 | 0.15 | max 19 % |
| AV1 1080p -> `h264_vaapi` 720p | 462 | 0.23 | max 7 % |
| VP9 1080p -> `h264_vaapi` 720p | ~420 | 0.3 | - |
| software H.264 1080p -> `libx264` 720p veryfast (reference) | 465 | **7.87** | - |

Parallel: 4 x (H.264 1080p -> H.264 720p, 1800 frames each) + 1 x (HEVC 10-bit 2160p -> H.264
1080p, 900 frames) finished in 20.6 s wall, all exit 0: every 30 fps stream ran at about 2.9x
realtime while 5 ran at once (>= 87 fps per 1080p stream). This is an ffmpeg throughput result, not
a Jellyfin client test; the four-viewer test is Phase 6.

`gpu_busy_percent` reports the graphics engine, not the VCN video engine, so it under-reports video
load (AV1 encode shows 0-1 %). VCN utilisation needs per-process `drm-engine-*` counters
(`/proc/<pid>/fdinfo`) - Phase 6 monitoring.

### Tone mapping (HDR10 -> SDR)

- Vulkan/libplacebo pipeline as used by Jellyfin on AMD (`hwmap=derive_device=vulkan,libplacebo`):
  `VK_ERROR_INVALID_DRM_FORMAT_MODIFIER_PLANE_LAYOUT_EXT` when mapping the VA-API surface.
- VA-API `tonemap_vaapi`: "Failed to configure output pad" (the generated test file also lacked
  complete HDR colour tags).
- The library has no HDR content (2026-11-11: all H.264 8-bit SDR <= 1080p, one VP8 1080p), so
  tone mapping stays **off**. Re-test with a real HDR10 file before enabling it.

## Jellyfin settings (applied by `scripts/configure-transcoding.py`)

| Setting | Value | Reason |
|---|---|---|
| Hardware acceleration | VA-API, `/dev/dri/renderD128` | verified above |
| Hardware decoding | H.264, HEVC, VP9, AV1; 10-bit HEVC + VP9 on | verified above; MPEG-2/VC-1/VP8 decode in software |
| Hardware encoding | on | verified |
| Allow HEVC / AV1 encoding | off | H.264 output plays on every client; revisit with client tests |
| Tone mapping | off | failed, and no HDR content |

## Verified in Jellyfin (2026-11-11, after `gpu.enabled: true`)

- Pod: uid 1000, groups 1000 + 992, `privileged: false`, `allowPrivilegeEscalation: false`, all
  capabilities dropped, limit `devic.es/dri-render: 1`; `/dev/dri` contains only `renderD128`.
  vainfo in the Jellyfin container: same 17 lines as above.
- `scripts/configure-transcoding.py`: applied 2 settings (`HardwareAccelerationType` none -> vaapi,
  `HardwareDecodingCodecs` [h264, vc1] -> [h264, hevc, vp9, av1]); second run: no change.
- Forced transcodes through the Jellyfin API (H.264, 960 px, 1.5 Mbit/s), from the `FFmpeg.Transcode-*`
  logs:

| Source (library) | Pipeline | Speed | Pod CPU while encoding | ffmpeg errors |
|---|---|---|---|---|
| H.264 1280x720 | `-hwaccel vaapi` -> `scale_vaapi` -> `h264_vaapi` | 817 fps, 31.6x | 0.36 cores | 0 |
| VP8 1920x1080 | software decode -> `h264_vaapi` | 723 fps, 28x | **6.0 cores (the pod limit)** | 0 |

CPU is measured from the pod cgroup (`cpu.stat`) over 12 s while ffmpeg encodes ahead at full speed
(throttling off); idle pod: 0.01 cores. At realtime playback the cost is a fraction of this, but a
VP8 (or MPEG-2/VC-1) transcode runs at the 6-core limit until it has encoded ahead. Phase 6 measures
this with real clients and decides on transcode throttling.

## Capacity

No capacity is claimed. The four-viewer target (one 4K Direct Play, one 1080p Direct Play, two
1080p transcodes) is measured in Phase 6 and recorded here with the exact conditions.
