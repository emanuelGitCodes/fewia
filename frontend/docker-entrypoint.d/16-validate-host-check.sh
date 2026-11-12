#!/bin/sh
set -e

# Validate only. Unset means off. The rejected value is never printed.
case "${FEWIA_WEB_HOST_CHECK-off}" in
    off|local)
        ;;
    *)
        printf '%s\n' 'Invalid FEWIA_WEB_HOST_CHECK.' >&2
        exit 1
        ;;
esac
