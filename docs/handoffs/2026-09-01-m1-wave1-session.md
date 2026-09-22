# Session handover — M1 Wave 1, 2026-09-01

For a fresh Claude Code session picking this up. Read this in full before doing anything.
Also read `CLAUDE.md`, `docs/ROADMAP.md`, and `docs/MISTAKES.md` as usual session-start
practice — this file is the addition on top of those for exactly where the *previous*
session left off.

## Standing instruction from Sebastian — read this first

**Do not go past Wave 1** of `docs/plans/M1.md` (T1–T3, T8) without him explicitly saying
so. Wave 2 (T4–T7) has not been authorized.

**Do not spawn subagents to implement tasks on this project**, even ones that look
mechanical or well-specified. Sebastian corrected this directly last session: the whole
point of this project for him is making the design/implementation calls himself and
getting immediate reaction, not having work handed back finished. This is saved as a
persistent memory (`feedback_no_subagents_for_execute_tasks.md`) so it should already be
loaded, but it's restated here because the damage from the mistake this file exists to
correct is still being worked through — see below. Investigative/fact-finding work (a
spike verifying how a live system behaves) is fine to do directly, still not via subagent.

## What actually happened last session

1. **T1** (Wave 0 spike, U-13) was run directly (not via subagent) — a container was
   started by hand, admin-token bootstrap and retention behavior were verified live, then
   torn down. Output: `docs/spikes/U-13-core-token-bootstrap.md`. This one is solid and
   doesn't need redoing for correctness — but Sebastian has since said he wants to redo
   the *hands-on* part himself for the learning value (see "In progress" below).

2. **T2, T3, T8** (Wave 1) were built by three parallel background subagents, dispatched
   without being asked. This was a mistake — Sebastian pointed out it defeated the reason
   he does this project (see standing instruction above). The files these agents produced
   are still on disk and are **functionally solid** (verified against a live Docker
   daemon, tests pass, `ruff` clean) — nothing is being thrown away — but they were never
   reviewed by Sebastian at decision-point granularity, so a walkthrough is underway to
   go back through the choices each task made, have him react to each one (right / wrong
   / partially right, same as any other design call), and fix what doesn't hold up.

3. **T2's walkthrough is done** — four decisions were surfaced, Sebastian reacted to all
   four, and the corrections are agreed but **not yet applied to the actual files**:

   - **#1 (bootstrap idempotency) — wrong, fix agreed.** `scripts/bootstrap_influx_token.py`
     currently treats "InfluxDB says a token already exists" (the 409 case) as a
     successful bootstrap. That's wrong: the server having a token doesn't mean *we*
     possess its value — if `.env` is lost while the server's volume persists, this
     silently "succeeds" with an empty `INFLUX_TOKEN`. **Fix**: persisted token in `.env`
     is the source of truth; on start, if a token is present, verify it actually
     authenticates (one cheap authenticated call — don't just trust a non-empty string,
     since a stale token from a wiped-and-restored volume would pass a naive check); if
     no token is present, attempt creation; if creation 409s, **fail loudly** (don't paper
     over it) — the operator needs to know they're in an unrecoverable-without-intervention
     state (no local token, but the server already has one it won't hand back). The
     existing stdout-text pattern-match for detecting the CLI's 409 (the CLI exits 0 even
     on this failure — a genuine finding, not something to design around) stays, but only
     as an isolated, clearly-marked workaround for that one CLI quirk — ideally with an
     integration test covering it.
   - **#2 (healthcheck via `--disable-authz health`) — approved as-is.** Confirmed right:
     health/liveness checks shouldn't depend on secrets or token validity. Still need to
     add: an integration test confirming *only* `/health` works unauthenticated and every
     other endpoint still correctly 401s without a token.
   - **#3 (CLI over Python client for token creation) — approved as-is.** Already
     documented in T2's handoff as a deliberate, isolated exception to the ADR-0003
     Python-over-HTTP preference, since admin-token bootstrap isn't exposed by
     `influxdb3-python`. No change needed.
   - **#4 (`.env.example` retention values) — wrong, fix agreed, plus a correction to a
     mistake in my own reasoning.** The file currently sets
     `INFLUX_RAW_RETENTION=365d` and `INFLUX_ROLLUP_RETENTION=365d` — equal values, which
     defeats the entire point of the rollup tier (it's supposed to *outlive* raw once a
     bucket freezes, same shape as ADR-0011's plant policy of 9mo raw / 1y rollup).
     **Fix**: keep raw at 365d (independently justified — it's sized so all six
     experiment windows clear it with margin, per `docs/plans/M1.md`'s "three calls" —
     don't undo that), and raise rollup above it. Sebastian proposed **5 years** for the
     local rollup value, reasoning "comfortably longer than raw, no real constraint ties
     it to a specific number since this is local/demo data" — that's an honest, sufficient
     reason and doesn't need to match any particular ratio. Confirmed accepted.
     **Separately**: `.env.example`'s existing comment claims the plant-policy rollup
     value (1 year) is "twelve times" the raw value (9 months). **That's an arithmetic
     error** — 12 months ÷ 9 months = 1.33×, not 12×. The subagent that wrote it made the
     error; I (the previous session) repeated it without checking when first discussing
     this with Sebastian. **This is a MISTAKES.md-worthy entry once tracking files are
     being written again** (T11, later — tracking files are explicitly not to be touched
     by any task except T11 per the plan's tracking-file rule).
     **Also flagged, not yet decided**: whether the not-yet-built T4 (Influx init script)
     should treat an empty `INFLUX_PINNED_RETENTION` value by *omitting* the
     `--retention-period` flag entirely, versus passing an empty string — these aren't
     guaranteed to behave identically on the CLI and it's worth deciding deliberately
     rather than discovering it as a T4 surprise. Not blocking right now since T4 is
     Wave 2.

   **None of these four fixes have been written to disk yet** — `scripts/bootstrap_influx_token.py`
   and `.env.example` still reflect the original subagent output. That's the first thing
   to do once the hands-on walkthrough below is finished (or in parallel, Sebastian's
   call).

4. **T3 and T8 have not been walked through yet.** They exist on disk
   (`docs/schema.md`; `pipeline/rollup.py` + `tests/unit/test_rollup.py`, 12/12 tests
   passing) but no decision-by-decision review has happened for either — same treatment
   as T2 is still owed to both.

## In progress when the session ended

Sebastian asked to redo the T1 spike **by hand, himself**, for the learning value —
typing the `docker run`/CLI commands rather than being told the answer. A 6-step plan was
proposed and agreed on:

1. Pull the pinned image (`influxdb:3.11.2-core`), confirm the version — the point being
   `latest` currently resolves to InfluxDB 2.x, not 3.x (contradicts ADR-0008).
2. Start the container by hand with `docker run` (not compose) — required flags
   `--node-id`, `--object-store file`, `--data-dir`, plus a port mapping.
3. Hit an endpoint unauthenticated, see the 401 — Core does *not* auto-mint a token on
   first boot, contrary to what ADR-0008/0009 assumed.
4. Create the admin token non-interactively (`influxdb3 create token --admin` via
   `docker exec`), then try it a second time and observe the 409-but-exit-0 behavior.
5. Prove retention behaviorally: create a throwaway 1-hour-retention database, write a
   point at `now - 2h` and one at `now - 5m`, query both back, see only the recent one.
6. Clean up — remove the container, volume, network.

**The session ended on a pending question: which shell is Sebastian using** (PowerShell,
Git Bash, or cmd) — this matters because Git Bash mangles Unix-style paths like
`/var/lib/influxdb3` into Windows paths (hit this directly during the original T1 spike,
worked around with `MSYS_NO_PATHCONV=1`; PowerShell/cmd don't have this problem, but the
command syntax and flag quoting differ). **Ask this before giving any commands** — don't
assume from `CLAUDE.md`'s "PowerShell primary" note, since Sebastian may prefer Git Bash
for this exercise.

**Guidance for how to run this walkthrough**: this is explicitly hands-on-for-Sebastian —
give him the command and the reasoning for the next step, let him run it and paste back
the output, then explain what it means before moving to the next step. Don't run these
commands via the Bash tool yourself; that would defeat the point exactly the same way the
subagent delegation did.

## Current environment state (verify before trusting — this is a snapshot)

- **Docker Desktop is running.** Two containers from T2's compose stack are up and
  healthy: `dac-influxdb` (`influxdb:3.11.2-core`) and `dac-postgres`
  (`postgres:16.6`), both started ~13 hours before this handover was written. A live,
  bootstrapped `.env` exists in the repo root (gitignored, not shown in `git status`).
  These are separate from the hands-on `docker run` exercise above (which should use its
  own container name, not `dac-influxdb`, to avoid port/name collisions) — Sebastian
  may want them stopped first; ask rather than assuming either way.
- **Nothing has been committed.** `git status --short` shows:
  ```
   M .gitignore
   M pyproject.toml
   M requirements.txt
  ?? .env.example
  ?? docker-compose.yml
  ?? docs/schema.md
  ?? docs/spikes/
  ?? pipeline/rollup.py
  ?? scripts/bootstrap_influx_token.py
  ?? tests/
  ```
  (plus this handoff file itself, once saved). The plan's "commit after each wave" rule
  applies once Wave 1 is actually reviewed and fixed — not yet.

## Suggested next steps, in order

1. Ask which shell, run the 6-step manual walkthrough with Sebastian driving.
2. Apply the two agreed T2 fixes (`scripts/bootstrap_influx_token.py`,
   `.env.example`) — as a normal back-and-forth edit, not a subagent, ideally with
   Sebastian reviewing the diff before it's considered settled.
3. Walk through T3 (`docs/schema.md`) and T8 (`pipeline/rollup.py`) the same way T2 was
   walked through — surface the choices made, let him react, fix what doesn't hold up.
4. Only once all of Wave 1 has actually been reviewed this way: ask whether to commit the
   Wave 1 checkpoint, per the plan's commit-per-wave rule. Still do not start Wave 2
   without an explicit go-ahead.
