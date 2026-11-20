# Pulse V2 — Alert & Collaboration Workspace

Local demonstration of a shared, real-time alert workflow with English Web UI and independent Web windows. V2 removes the Tkinter desktop program entirely. The existing workspace, chat, attachment, directory, alert simulator and SQLite models are retained.

## 1. Run locally

**Requirements:** Python 3.10+ and a recent Chrome or Edge browser. The application has no third-party Python or npm runtime dependencies. Finsemble is optional and not bundled.

On Windows, unzip the complete `pulse` folder and double-click `start_demo.bat`, or open a terminal in that folder:

```powershell
python start_demo.py
```

The Python server listens on `http://127.0.0.1:8765` and opens the workspace. Keep the terminal running. Stop with Ctrl+C. To use another port: `python start_demo.py --port 8766`. To start without a browser: `python server.py`. The SQLite database is created in `data/pulse.sqlite3` on first use. Do not delete it unless you want to reset the demonstration.

## 2. Choose the popup mode

### A. Browser — independent window (recommended demo)

1. Open the workspace and click **Popup mode: In-page** in the left navigation so that it becomes **Popup mode: Window**.
2. In Chrome or Edge, allow pop-ups and redirects for the exact local site `http://127.0.0.1:8765`. In a managed browser this may require an approved policy exception; do not try to bypass company controls.
3. Keep the workspace open. Publish an alert from the simulator.
4. The client attempts to open a dedicated Web window, using the same CSS and alert detail, chat, participant, activity and attachment components as the workspace. If the browser blocks it, a normal in-page alert card appears instead. Click its **Open window ↗** action to retry with a user gesture.
5. A named window is reused for the same SOEID and alert ID within the adapter session. Automatic events do not deliberately call focus on an existing browser window, although the browser controls creation and focus of new windows.

The browser preference is stored per demo SOEID in localStorage. Switch back to In-page mode at any time. You can also open the selected alert in an independent window with **Open window ↗** from the details panel, without changing the automatic mode.

### B. Browser — background listener (workspace may be closed)

Open `http://127.0.0.1:8765/listener.html?user=am23456` in a browser window/tab. Wait for **Live connected**. This page receives SSE messages and launches independent alert windows. Keep the listener tab open; you can close the regular workspace. If the browser prevents opening the window automatically, use the **Open alert ↗** button in the listener's recent notification list. The listener is NOT an OS service and does not run when its tab or the entire browser is closed. Background tabs can be throttled by the browser.

If you open the listener from the workspace's **Background listener** navigation link, the workspace enters **Popup mode: Listener** to avoid double notifications. The listener's **Open alert inbox** link likewise opens a workspace with automatic popup delivery delegated to the listener (`&listener=1`). Use only one listening source per SOEID. If you close the listener and keep its workspace open, click **Popup mode: Listener** to return to normal workspace delivery. Two unrelated tabs configured as separate listeners are not coordinated in this prototype.

### C. Finsemble — managed Web window

The same `/alert-popup.html` page is opened by the Finsemble `AppsClient.spawn` API (or legacy `LauncherClient`). The always-running Finsemble App Service owns notification delivery, even when the workspace is not open. See `finsemble/README.md` for the configuration, limitations, and integration checklist. This is a contract-tested integration example, **not a verified installation in your company's Finsemble platform**.

## 3. Full demonstration

Open the following user workspaces in separate windows/tabs before publishing. Click Popup mode: Window in each workspace to see standalone windows, or keep In-page mode to demonstrate cards. If pop-ups are blocked, use the fallback.

| User | URL | Scenario |
|---|---|---|
| Alex Morgan | http://127.0.0.1:8765/?user=am23456 | Subscriber / owner |
| Sarah Chen | http://127.0.0.1:8765/?user=sc12345 | Subscriber / collaborator |
| Daniel Lee | http://127.0.0.1:8765/?user=dl34567 | Mentioned colleague |
| Michael Brown | http://127.0.0.1:8765/?user=mb45678 | Invited colleague |
| Alert simulator | http://127.0.0.1:8765/mock | Mock alert source |

1. Wait until each client shows **Live connected**. Open the simulator, select **Trade validation** and leave Alex and Sarah selected; click **Publish alert**.
2. Alex and Sarah receive the same alert. Daniel and Michael do not receive it initially.
3. Alex clicks **Take ownership**. Sarah sees In progress / Alex Morgan. Concurrent claims are resolved by a SQLite transaction on the backend.
4. Alex sends a message; Sarah sees it without refreshing. In an alert window, open **Activity** to see the event log; **Discussion** shows the shared chat.
5. In Discussion, type `@dl` and pick Daniel Lee (`dl34567`), add a message, and click Send. Daniel receives a mention popup, even though he was not originally subscribed. He can view the existing discussion. You can run Daniel using only the background listener to demonstrate this.
6. Click **+ Add people**, search `mb45678`, select Michael and Invite. Michael receives an invitation popup.
7. Click **+ Attach** or drag the included `samples/support_update.eml` onto the message composer. Other participants can expand **Email preview** or download the original. `.msg` uploads preserve the file but do not parse it; Outlook drag-and-drop support depends on the Outlook / container version. Use ordinary saved files for a predictable demo.
8. Alex clicks **Resolve**, supplies a resolution summary, and submits. All viewers update to Resolved. V2 independent windows remain available after resolution so chat drafts and history are not lost. Dismiss closes only the current user's view, never the shared alert.
9. Open History from a workspace to revisit the same discussion, files, audit timeline, and resolution.

The standalone **Snooze 5 min** temporarily hides the alert details inside the open window; click **Resume now** or wait five minutes. It resumes immediately on resolution. Closing that window cancels its timer. In-page Snooze and notification read/dismiss are local to the open workspace session. No durable snooze scheduler is included.

## 4. Architecture and project layout

```text
Alert Simulator / future external alert producer
    -> Python ThreadingHTTPServer (REST)
    -> SQLite (alerts, members, messages, attachments, activity, events)
    -> SSE (per SOEID, reconnect cursor)
       -> Workspace / in-page cards / browser adapter
       -> Browser listener OR Finsemble App Service
           -> Desktop adapter -> independent /alert-popup.html
       -> Open alert windows -> live state and discussion updates
```

```text
pulse/
  server.py                  Python standard-library backend
  start_demo.py/.bat         Launch server and default browser
  static/
    index.html               Workspace and history
    mock.html                Alert simulator
    alert-popup.html         Independent Web alert + discussion window
    listener.html            Browser / Finsemble background listener
    listener.js              Notification delivery and retry
    adapters/desktop.js      BrowserAdapter / FinsembleAdapter
    app.js                   Shared alert UI, actions, chat, people, attachments
    style.css                Shared visual design
  finsemble/
    appd.json                Example app + app service registration
    README.md                Integration instructions and caveats
  samples/support_update.eml
  tests/                     Backend, JS contract tests, optional Playwright flows
  TEST_REPORT.md
```

`server.py` uses a loopback-only bind by default, so this is a local demonstration. The mock alert publication is `POST /api/alerts`; replace that mock source later with a server-side message consumption adapter. REST endpoints include `/api/users`, `/api/snapshot`, `/api/alerts/{id}`, `/api/alerts/{id}/actions`, `/api/alerts/{id}/messages`, `/api/alerts/{id}/invite`, `/api/alerts/{id}/attachments`, `/api/attachments/{id}`, `/api/events` and `/api/stream`. Demo user identity is passed in the `user` query parameter. A snapshot supplies the latest event cursor, and SSE replays missed events on reconnect within the same session. Older alerts remain in the inbox after a completely new client launch rather than generating old popups. Listener failure to launch a window is shown in its recent-event list (and logged in console); production needs monitored delivery/retry/ack policies.

## 5. Test locally

Backend tests (no additional dependencies):

```bash
python -m unittest tests.test_api -v
```

UI and adapter contracts (Node.js 18+ is only a development/test dependency):

```bash
node --test tests/*.cjs
```

Optional real browser E2E tests (browser test tooling is not a runtime dependency):

```bash
python -m pip install playwright
python -m playwright install chromium
python -m tests.browser_flow
python -m tests.window_flow
```

See `TEST_REPORT.md` for exact executed results and blockers. Browser tests in this development environment were blocked by its managed-browser policy. The Finsemble SDK is not installed here; adapters were tested with mock FSBL clients. Verify real browser layout and client integration on Windows.

## 6. Prototype boundaries

Fictional employee directory and insecure demo user switching are intentional. Do not expose this server on a shared network, use real credentials, or upload production emails / trade data. There is no corporate SSO, LDAP/Entra/Teams integration, malware scanning, production file ACL model, multi-host streaming broker or automatic startup with Windows. Uploaded content is stored locally in SQLite (10 MB per file); `.eml` is parsed, `.msg` is not. The future employee directory and corporate identity must be supplied by the platform team. Retained attachments and messages are accessible to alert participants in this demo. Production needs audited permissions, TLS, origin policy, connection recovery, monitoring, retention and security review.
"# pulsedemo" 
