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

**Test Log** — the actual entry, and the heart of the app:

- Subject, module/feature, test type, severity, environment, build tested
- Steps to reproduce, expected result, actual result
- **Evidence table** — attach screenshots and screen recordings; images and video preview inline
  on the form, and external Loom/Drive links are supported for anything too big to upload
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
