# Pulse V2 — test report

## Executed checks

Environment: Linux container, Python 3.13, Node.js 22, managed Chromium. Tests used temporary SQLite databases and fictional identities only.

| Suite | Result | Scope |
|---|---:|---|
| `python -m unittest tests.test_api -v` | 9/9 passed | HTTP API, concurrent claim, permissions, chat, mention, invitation, email upload/download, SSE replay, resolution/release, persistence, validation, routes |
| `node --test tests/frontend_logic.cjs` | 7/7 passed | Existing Web UI logic, in-page popup, HTML escaping, mention search, state updates, history and attachment rendering |
| `node --test tests/desktop_adapter.cjs` | 7/7 passed | Browser named window, blocked-popup result, reopen and focus policy; mocked Finsemble readiness, spawn, show, deduplication, error handling, close and legacy API alias |
| `node --test tests/notification_routing.cjs` | 6/6 passed | In-page / independent-window routing, blocked-window fallback, listener ownership, standalone scoped updates, duplicate and stale resolved event handling |
| `node --test tests/listener_logic.cjs` | 4/4 passed | Snapshot cursor, SSE setup, mention routing, event replay dedupe, blocked-popup manual fallback, stale resolved alert suppression |
| **Total** | **33/33 passed** | API and JavaScript contract/logic tests, not real-browser E2E |

Python compile, all production JavaScript syntax checks and JSON parsing also passed. No runtime third-party modules are required.

## Real browser tests — blocked

Both `tests.browser_flow` and `tests.window_flow` were attempted with installed Chromium and Playwright. They stopped on the first `page.goto()` because the managed Chromium installation returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` on the local HTTP URL. The system policy contains a URL blocklist. No changes to that policy were attempted. Therefore browser layout, actual popup policy, true multi-window rendering, and browser end-to-end workflow have not been verified in this environment. The test scripts are included for an approved local Windows environment. Do not interpret the JavaScript contract tests as browser visual tests.

## Finsemble — contract tests only

The actual proprietary Finsemble host was not available in this environment. The adapter's SDK interactions were tested against mock FSBL clients using the documented callback signatures. The sample AppD JSON parses successfully, but has not been imported into a real Finsemble instance. Validate registration, host version, privileges, visibility, focus/placement, SSE connection and SSO in the corporate test platform. See `finsemble/README.md` for the acceptance checklist. No claim of production readiness is made.

## Known prototype choices

- All UI is Web HTML/CSS/JavaScript; no Tkinter program remains.
- Browser popup blocker fallback is an in-page card, or a manual open action on the separate listener page.
- Browser background listening requires the listener tab to remain open. Finsemble can use a registered App Service while the platform runs.
- Independent windows remain open on resolution, so drafts and history are preserved. Closing the window is local only. Standalone snooze hides details temporarily and requires the window to stay open.
- Demo identity, local-only SQLite, mock directory, `.msg` opaque file storage, no corporate SSO or security scanning. No production data should be used.
