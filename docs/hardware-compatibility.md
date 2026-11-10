# Hardware compatibility report

Status: **Phase 0 facts measured; codec support NOT yet verified.** Hardware transcoding is
configured only for codecs that `vainfo` and real ffmpeg runs confirm in Phase 4.

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

## Expected (vendor documentation, UNVERIFIED)

VCN 4.0 is documented by AMD/Mesa for: decode H.264, HEVC 8/10-bit, VP9 8/10-bit, AV1 8/10-bit;
encode H.264, HEVC 8/10-bit, AV1. MPEG-2, VC-1 and others: to be checked with `vainfo`.
Jellyfin uses the Mesa radeonsi VA-API driver shipped in the official image.

## Phase 4 verification plan

1. Device plugin running on mr2; node allocatable `devic.es/dri-render: 1`.
2. `vainfo --display drm --device /dev/dri/renderD128` in the Jellyfin pod -> list of
   `VAProfile*/VAEntrypointVLD` (decode) and `VAEntrypointEncSlice*` (encode). Record verbatim here.
3. ffmpeg tests in the pod with the image's `jellyfin-ffmpeg` (`-hwaccel vaapi`,
   `h264_vaapi` / `hevc_vaapi` / `av1_vaapi`), each with the source codecs present in the library;
   record fps, CPU %, `gpu_busy_percent`, errors.
4. Tone mapping (HDR -> SDR): VA-API/OpenCL/Vulkan options per Jellyfin docs, tested only if HDR
   content exists.
5. Jellyfin settings: Hardware acceleration `VA-API`, device `/dev/dri/renderD128`, enable only
   verified decode codecs, hardware encoding on, `AllowHevcEncoding`/`AllowAv1Encoding` only if
   the target clients support them.

## Capacity

No capacity is claimed. The four-viewer target (one 4K Direct Play, one 1080p Direct Play, two
1080p transcodes) is measured in Phase 6 and recorded here with the exact conditions.
