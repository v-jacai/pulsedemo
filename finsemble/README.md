# Finsemble integration — V2 prototype

This package uses the host-injected `window.FSBL` interface found in registered Finsemble Web apps. No Electron process or native desktop UI is started by Pulse. `appd.json` is an illustrative modern AppD configuration fragment for Finsemble's FDC3-style app registration. Merge its three records into the actual platform's app directory using your Finsemble administrator's deployment process. Do not replace the corporate app directory. The exact version, app service permission and registration schema must be verified in the host. Older releases use the legacy `finsemble.appd`/`manifest` schema; this sample does not claim universal compatibility. io.Connect Desktop uses a different SDK; it is not implemented here.

## Three registered apps

- **Pulse Workspace**: ordinary Web app, `/`.
- **Pulse Alert Popup**: Web app with the independent alert page, `/alert-popup.html`. The listener supplies an alert URL on spawn. The popup is not a normal standalone launcher entry unless an alert ID is supplied; hide it from the launcher through your host's configuration. It is not added to the saved workspace by the adapter.
- **Pulse Alert Listener**: `appService: true` in `hostManifests.Finsemble`, launched in the `preuser` stage after authentication, invisible under normal host configuration. It connects to the Python SSE stream. `waitForInitialization: false` avoids blocking host boot if the prototype server is offline. It retries the initial snapshot if the server is not ready.

## Setup

1. Start the Pulse local Python server with `python server.py`.
2. Have the platform team confirm its Finsemble version, whether it exposes `FSBL.Clients.AppsClient` or `LauncherClient`, and whether registered Web apps can reach the service URL and call `getActiveDescriptors`, `spawn`, `showWindow` and `WindowClient.close`.
3. Register the three apps with the sample URL and demo user. Ensure FSBL is injected by the host and verify the `onReady` event. `host=finsemble` explicitly selects the Finsemble adapter; an injected FSBL also selects it. No browser fallback is silently substituted when this host mode is selected.
4. The supplied demo configuration hardcodes `am23456`; change the `user` query parameter in both the workspace and listener registrations to the selected demo user. For real deployment replace the demo user query parameter with a verified corporate SOEID established through the host's approved SSO mechanism and enforced by the server. Do not use this demonstration identity mechanism for company users.
5. Launch the host and verify that the app service is connected. Publish an alert to the corresponding user from `/mock` and check that an independent Web window appears even without the workspace open. Test mention, invite, claim, resolution and dismissal. If testing a separate Windows session or workstation, use an approved test API host instead of loopback; each workstation's loopback is its own server. The demo backend is deliberately not configured for network deployment.

## Native host calls

`static/adapters/desktop.js` waits for `FSBL.addEventListener('onReady', ...)` (or `FSBLReady` event). It resolves the modern `AppsClient` or legacy `LauncherClient`, queries running window descriptors, and calls `spawn('Pulse Alert Popup', params)` with a deterministic SOEID/alert-based `name`, dynamic URL and spawn data. An already-open matching window is shown rather than respawned. A concurrent-open guard prevents duplicate spawns within the listener instance. The configured app has `alwaysOnTop: true`; automatic spawn and show set `autoFocus: false`. The real host security policy, DPI and available monitor size may override these requests. Manual opens may focus an existing window. Window close uses the host's WindowClient; it never resolves an alert. Existing windows retain their chat state and update using SSE; repeated mentions of an already-open alert update the reason banner but do not recreate the window or deliberately interrupt current editing.

`static/listener.js` filters `alert_created`, `mention` and `invited` events. State changes and ordinary chat messages update the existing windows via their own SSE stream. Resolved stale notifications do not launch windows. This prototype launches all severity levels to simplify the demo. A production severity-based policy, flood control, notification center integration and persistent notification acknowledgements remain follow-up items. The listener uses a fresh snapshot at launch (no old notification replay) and resumes from its cursor on in-session connection errors. Failed opens are logged and recorded in the listener list; the hidden service does not currently generate a separate native fallback toast. Inspect its development console and the alert inbox for failures.

## Required acceptance tests in the actual platform

- Background app service starts after sign-in with the correct SOEID, including with no workspace open; exits with the host.
- Web alert spawns once per user and alert. Test close/reopen, repeated mentions and concurrent arrivals.
- Validate focus behavior while typing in another application, multi-monitor placement, DPI, titlebar, always-on-top policy and resizing.
- SSE connection works with corporate proxy, CSP, session refresh and network reconnection.
- Simultaneous subscribers receive updates from server; a newly invited person receives a window, subject to backend authorization.
- Attach an approved mock email, download it, and verify corporate attachment security and drag/drop support.
- Confirm Web window closes without altering shared alert status; no restored stale popup on workspace reload.

## Official references checked

- https://finsemble.interop.io/docs/productivity/API-tutorials-and-refs/extending/AppServices/
- https://finsemble.interop.io/docs/reference/typedocs/modules/AppsClient/
- https://finsemble.interop.io/docs/reference/typedocs/modules/WindowClient/
- https://finsemble.interop.io/docs/productivity/UsingFinsembleAPI/
- https://finsemble.interop.io/docs/add-apps/html/integratingHTMLApplications/
- https://finsemble.interop.io/docs/reference/ConfigReference/
