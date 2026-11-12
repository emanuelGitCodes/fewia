#!/bin/sh
set -e

# Write fixed map text for the validated mode. The value never enters the config.
conf=/etc/nginx/conf.d/00-fewia-host-check.conf

case "${FEWIA_WEB_HOST_CHECK-off}" in
    off)
        cat > "$conf" <<'EOF'
map $host $fewia_host_denied {
    default 0;
}
EOF
        ;;
    local)
        cat > "$conf" <<'EOF'
map $host $fewia_host_denied {
    default 1;
    localhost 0;
    127.0.0.1 0;
    "[::1]" 0;
}
EOF
        ;;
    *)
        printf '%s\n' 'Invalid FEWIA_WEB_HOST_CHECK.' >&2
        exit 1
        ;;
esac
