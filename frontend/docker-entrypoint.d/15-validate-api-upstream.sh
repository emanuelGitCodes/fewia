#!/bin/sh

case "${FEWIA_API_UPSTREAM-}" in
    api:8000|127.0.0.1:8000)
        exit 0
        ;;
    *)
        printf '%s\n' 'Invalid FEWIA_API_UPSTREAM.' >&2
        exit 1
        ;;
esac
