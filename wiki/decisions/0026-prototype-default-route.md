# 0026 — `/prototype` is the default route

- Date: 2026-11-05
- Status: accepted

## Decision

A visit to `/` lands on `/prototype`. The address bar shows `/prototype`. The
older `App` page stays reachable at `/app`. Agents and developers MUST start a
local test or demo at `http://127.0.0.1:5173/prototype`.

## Options considered

1. Keep `/` on `App` and only test at `/prototype` — a person who opens the
   base URL still lands on the older page.
2. Render the prototype at `/` with no redirect — two paths would show one page,
   and the Kroger return URL already names `/prototype`.
3. Redirect in nginx and in the client — chosen. The nginx rule covers Compose,
   and the client rule covers the Vite dev server.

## Reason

The owner asked on 2026-11-05 that `/prototype` be the default route for all
testing. [PR 472](https://github.com/emanuelGitCodes/fewia/pull/472) ships it.

## Consequences

- `frontend/nginx.conf` returns `302 /prototype` for `/`. `absolute_redirect off;`
  keeps the host port, because nginx listens on 8080 and Compose publishes 5173.
- `canonicalPath` in `frontend/src/rootView.tsx` maps `/` to `/prototype`.
- Playwright tests that exercise `App` MUST open `/app`.
- No automated test covers the nginx rule or the `replaceState` call.
