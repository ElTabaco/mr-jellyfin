#!/bin/sh
# Jellyfin preflight (init container). Runs as the Jellyfin UID before the server starts.
#  1. /media must be an NFS mount and every library folder must exist and be readable.
#  2. /config and /cache must be writable.
#  3. First boot only: seed config files that do not exist yet. Existing files are never changed.
# Exit code != 0 keeps the pod in Init:Error, so Jellyfin never starts without its media.
set -eu

fail() {
    echo "PREFLIGHT FAIL: $*" >&2
    exit 1
}

echo "preflight: uid=$(id -u) gid=$(id -g) groups=$(id -G)"

mount_type=$(awk '$2 == "/media" { print $3 }' /proc/mounts)
case "$mount_type" in
    nfs | nfs4) echo "preflight: /media is $mount_type" ;;
    *) fail "/media is not an NFS mount (type='${mount_type}')" ;;
esac

for lib in ${LIBRARIES:-}; do
    dir="/media/$lib"
    [ -d "$dir" ] || fail "library folder $dir does not exist on the NAS export"
    ls -A "$dir" > /dev/null 2>&1 || fail "library folder $dir is not readable by uid $(id -u)"
    echo "preflight: $dir ok"
done

for dir in /config /cache; do
    probe="$dir/.preflight-$$"
    if ! : > "$probe" 2> /dev/null; then
        fail "$dir is not writable by uid $(id -u)"
    fi
    rm -f "$probe"
done

mkdir -p /config/config

if [ "${SEED_ENABLE_METRICS:-false}" = "true" ] && [ ! -e /config/config/system.xml ]; then
    cat > /config/config/system.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<ServerConfiguration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <EnableMetrics>true</EnableMetrics>
</ServerConfiguration>
EOF
    echo "preflight: seeded config/system.xml (EnableMetrics=true)"
fi

if [ "${SEED_TRANSCODE_PATH:-false}" = "true" ] && [ ! -e /config/config/encoding.xml ]; then
    cat > /config/config/encoding.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<EncodingOptions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <TranscodingTempPath>/transcode</TranscodingTempPath>
</EncodingOptions>
EOF
    echo "preflight: seeded config/encoding.xml (TranscodingTempPath=/transcode)"
fi

if grep -q '<EnableMetrics>true</EnableMetrics>' /config/config/system.xml 2> /dev/null; then
    echo "preflight: metrics enabled"
else
    echo "preflight: WARN metrics disabled in system.xml (Dashboard > Networking or docs/operations.md)"
fi

echo "preflight: OK"
