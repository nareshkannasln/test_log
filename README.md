# Test Log

A Frappe app for keeping testing logs in one place — testers record what they tested with
screenshots and screen recordings, hand the whole run to a developer, and the developer updates
the status right on the same record.

Built for Frappe v15/v16.

## What it gives you

**Test Product** — the applications you test. Each one can carry a default developer, so logs
raised against it get routed automatically.

**Test Run** — the "sheet". A named batch of testing (`Sprint 42 regression sweep`) tied to a
product and build. It keeps a live count of its logs by status, and can be shared wholesale with
a developer in one action.

**Test Log Settings** — one switch turns on *tester mode*: a capture button on every screen with
screenshot, screen recording, snipping and offline logging behind it. See below.

**Test Log** — the actual entry, and the heart of the app:

- Subject, module/feature, test type, severity, environment, build tested
- Steps to reproduce, expected result, actual result
- **Evidence table** — attach screenshots and screen recordings; images and video preview inline
  on the form, and external Loom/Drive links are supported for anything too big to upload
- **Capture context** — for anything logged from the capture panel: the route and URL the tester
  was on, viewport, browser/OS, and the console errors the page threw
- **Status**: `Open → Ongoing → Fixed → Completed`, plus `Won't Fix` and `Reopened`
- Tester, assigned developer, target fix date
- Developer section: resolution notes, fixed-in-build, and auto-stamped resolved by/on

## How the handoff works

Setting **Assigned Developer** on a log (or saving via *Share with Developer*) does three things
in one step:

1. Shares the document with that user so they can open and edit it
2. Creates a ToDo assignment for them — priority is raised automatically for High/Critical severity
3. Notifies them

From a **Test Run**, *Share with Developer* shares the run **and every log inside it** at once,
with an optional note. That's the "share the sheet with the developer" flow.

Any status change notifies the other party — if a developer marks something Fixed, the tester
hears about it, and vice versa.

## Updating status

Three ways, so the developer always has the fastest one to hand:

- **On the form** — a Status button group offers only the valid next steps for the current status.
  Marking `Fixed` or `Won't Fix` prompts for a note, which lands in the Resolution field.
- **From the list** — tick several logs and use *Actions → Mark Ongoing / Fixed / Completed*.
- **Directly** — edit the Status field and save.

## Tester mode — logging without leaving the page

Switch **Enable Tester Mode** on in *Test Log Settings* and a capture button appears in the
bottom-right corner of every screen, desk and portal alike. It opens a panel down the right-hand
side of the page being tested — no dialog, no navigation, and the page behind it stays clickable,
because the tester is still using it.

The panel reads like a conversation: capture, say what went wrong, send. Each entry sent becomes
one Test Log in the current run, and the feed above the composer shows what has been filed so far.

**The tools, all native browser APIs — nothing to install:**

- **Screenshot** — grabs a frame of whatever screen or window the tester picks. The panel hides
  itself first, so it never ends up in the shot.
- **Snip & annotate** — capture, then crop to what matters, ring it in red, add arrows or freehand
  notes, and **pixelate anything that should not leave the machine** before it is attached.
- **Record screen** — with system and (optionally) microphone audio, a live timer, and an automatic
  stop at the size or time limit set in the settings.
- **Paste** — the tester's own OS snipping tool, straight into the text box. Drag-and-drop and file
  browse work too.

Each entry also carries, without anyone typing it: the route and URL, viewport, browser and OS,
and any Javascript errors the page threw beforehand. Those land in the log's *Capture Context*
section, which is usually the first thing a developer wants.

Under **Details** the tester can also pick the developer to hand the finding to. Sending it then
shares the log with them, puts it on their to-do list and notifies them — the same handoff the
form does. Left alone, it routes to the product's default developer.

`Ctrl+Shift+L` opens the panel from anywhere. Right-clicking the button offers to hide it for that
one user without touching anyone else's setup.

### Offline

Testing often happens on a laptop with the site running locally, or on a connection that comes and
goes. The panel is built for that:

1. Every entry is written to the browser's own database — screenshots and recordings included —
   **before** anything is sent.
2. It is only removed once the server has confirmed a Test Log for it.
3. Each attachment remembers its upload, so a retry never uploads a file twice.
4. Each entry carries a client id, so an entry the server already saw comes back as the same test
   log instead of a second one.

Offline, the strip at the top of the panel says so and entries stack up with a *Waiting* badge; the
count also shows on the button itself. When the site is reachable again they send themselves, with
backoff on network trouble. Something the server actually rejects stops and says why, with *Try
again* and *Discard* on the entry — it is never silently dropped, and never retried forever.

The tester's half-written entry is kept as a draft too, so a reload does not lose it.

## The Word report

Testing usually has to be handed over as a document, so the app writes one: **Word Report** on a
Test Run builds a `.docx` covering the whole sheet — run details and counts, then every log with
its description, steps, expected and actual result, and **its screenshots embedded inline** under
their captions. Recordings and other files are linked (Word cannot play video), external Loom or
Drive links come through as links, and the console errors are included.

There is the same button on a single Test Log, and one in the capture panel's header for the run
being tested. The document is attached to the record it describes, replacing the previous copy
rather than piling up, so the sheet and its evidence travel together.

For a handover that is a few findings from here and there rather than a whole run, tick them in
the Test Log list and use *Actions → Word Report*: one document with a contents page listing what
is in it, then a page per log with its evidence. Logs the tester cannot read are left out and
reported rather than failing the export.

Turn on **Keep a Report Attached to Each Run** in the settings and the run's document is refreshed
in the background whenever one of its logs changes — deduplicated per run, so a burst of entries
rebuilds it once.

No dependency is involved: the `.docx` is written directly, so it works on an offline machine too.

### Settings

*Test Log Settings* (single) controls the lot: who sees the button (all users, or the roles you
list — Tester and System Manager by default), the default product, run, severity and test type,
which capture tools are offered, recording and attachment limits, whether uploads are private,
whether page context and console errors are recorded, how often a waiting queue retries, and
whether a Word report is kept attached to every run.

Installing the app switches tester mode on for Tester and System Manager. Turning it off hides the
button for everyone, and it stays off across upgrades.

## Dashboard and export

The **Test Log** workspace shows number cards for Open / Ongoing / Fixed / Completed, a donut of
logs by status, and shortcuts including *Assigned to Me*.

The **Test Run Summary** report is the exportable sheet — one row per log, filterable by run,
product, status, severity, tester, developer and date range, with a column of resolved evidence
URLs. Use the report view's built-in **Export** for Excel or CSV.

## Roles

The app creates two roles on install:

- **Tester** — full create/read/write/delete on runs, logs and products
- **Developer** — read/write on test logs (so they can update status and add resolution notes),
  read-only on runs and products

## Installation

```bash
cd /path/to/your-bench
bench get-app https://github.com/<your-org>/test_log.git
bench --site <your-site> install-app test_log
```

## Development

```bash
cd apps/test_log
pre-commit install
```

## License

MIT
