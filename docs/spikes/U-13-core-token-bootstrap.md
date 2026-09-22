# Spike U-13 — InfluxDB 3 Core first-boot token behaviour

Date: 2026-08-31
Reads: ADR-0008, ADR-0009 (exception 1), `ASSUMPTIONS.md` U-13

Method: started the image by hand with `docker run` (not compose), on Windows 11 /
Docker Desktop 24.0.6, using `MSYS_NO_PATHCONV=1` to stop Git Bash mangling container
paths. Host port 18181 mapped to container 8181, one named volume, one bridge network.
Container, volume and network were removed at the end of the spike (see final section).

## 1. Which exact tag is the Core 3.x line, and is it a stable pin?

**Correction to ADR-0008's stated fact.** ADR-0008 (2026-08-23) claims `influxdb:latest`
"has pointed at 3 Core since 27 May 2026." That is not true today:

```
$ docker run --rm --entrypoint influxd influxdb:latest version
InfluxDB v2.9.1 (git: d4fa1941fd) build_date: 2026-05-11T20:49:03Z
```

`influxdb:latest` currently resolves to the 2.x line (config dirs `/etc/influxdb2`,
`/var/lib/influxdb2` are present in the image; there is no `influxdb3` binary on `PATH`).
Whether the tag pointed at 3.x briefly and moved back, or the ADR's claim was simply
wrong, is not determinable from here — but the tag is not a reliable pin regardless, which
was already the ADR's own conclusion for the pinning requirement. This is a finding for
T11 to carry into `MISTAKES.md` / flag against ADR-0008; it does not change the decision
(pin explicitly), only the evidence cited for it.

Core 3.x images live under the `-core` tag suffix. Docker Hub lists exact patch pins going
back to `3.0.0-core`; the current head is:

```
3.11.2-core   2026-08-21   sha256:f4a6d4a76f0ed0a196cc997da472cd0b7ae52a766430493a1bead807ab8c1217
```

**Recommended pin: `influxdb:3.11.2-core`.** It resolves and pulls cleanly:

```
$ docker pull influxdb:3.11.2-core
Status: Downloaded newer image for influxdb:3.11.2-core
$ docker run --rm --entrypoint influxdb3 influxdb:3.11.2-core --version
influxdb3 InfluxDB 3 Core, 3.11.2, revision 617521dc01dfed78a1e70185f80e55e027fd48de
```

`3-core` and `3.11-core` also exist as moving tags (same digest as `3.11.2-core` today)
but are not stable pins — use the full patch version.

## 2. What does the container require at startup?

Image entrypoint is `["influxdb3", "serve"]`; `--node-id` and `--object-store` are
required flags with no defaults (confirmed via `--help`: both listed under "Required").
Minimum working invocation:

```
influxdb3 serve --node-id node1 --object-store file --data-dir /var/lib/influxdb3
```

Startup log confirms `file` object store, catalog init, and completion in ~4s
(`startup time: 4023ms`). No built-in Docker `HEALTHCHECK` ships with the image
(`docker inspect ... Config.Healthcheck` is `null`) — T2 has to define one.

## 3. Does it mint an admin token on first boot, captured non-interactively?

**No — correction to ADR-0008/ADR-0009's stated mechanism.** Both ADRs assert Core
"mints its admin token on first boot." It does not: the server starts with no token, and
the first authenticated call after boot returns 401 even to `/health`:

```
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:18181/health
401
```

A token has to be explicitly requested, and that request **does** work non-interactively
— no TTY, no prompt:

```
$ docker exec influx-spike influxdb3 create token --admin
New token created successfully!
Token: apiv3_cicer0...
HTTP Requests Header: Authorization: Bearer apiv3_cicer0...
```

This is the command T2's bootstrap script runs (via `docker exec` or, since
`create token --admin` defaults to `--host http://127.0.0.1:8181`, equally callable from
the host against the mapped port once the container is reachable).

**Idempotency note for T2:** a second `create token --admin` call against a server that
already has one does **not** silently succeed or return the same token — it fails loudly:

```
$ docker exec influx-spike influxdb3 create token --admin
Failed to create token, error: ApiError { code: 409, message: "token name already exists, _admin" }
```

So the bootstrap script's "idempotent, no-ops on second run" behaviour (T2 acceptance
criteria) must be implemented as *catch the 409 and treat it as already-bootstrapped*,
not assumed for free — the server gives no idempotent success path itself. `--regenerate`
exists but issues a *new* token and invalidates the old one, which is not what an idempotent
bootstrap wants.

**Summary: works non-interactively, but the ADRs' "mints on first boot" framing is wrong.**
The correct framing is "the CLI can create the admin token non-interactively against a
running server, and the bootstrap script must call it once and treat 409 as success."

## 4. Does `create database --retention-period` exist, and what value syntax?

Yes, and it works as documented — one worked example, creating `spike_db` with a 1-hour
retention:

```
$ docker exec influx-spike influxdb3 create database --token "$TOKEN" \
    --retention-period 1h spike_db
Database "spike_db" created successfully
```

`1h` was accepted directly; duration syntax follows the common Rust/Go style (`d`, `h`,
`m` suffixes) based on the `--expiry` help text elsewhere in the CLI (`10d`, `1y`).

## 5. Does `show databases` / the configure API report retention back?

**No — [influxdb#27082](https://github.com/influxdata/influxdb/issues/27082) still
reproduces on 3.11.2**, not just the 3.7.0 the issue was filed against:

```
$ docker exec influx-spike influxdb3 show databases --token "$TOKEN"
+---------------+
| iox::database |
+---------------+
| _internal     |
| spike_db      |
+---------------+

$ curl -H "Authorization: Bearer $TOKEN" \
    "http://localhost:18181/api/v3/configure/database?format=json"
[{"iox::database":"_internal"},{"iox::database":"spike_db"}]
```

Neither surface carries the retention period. This directly confirms the plan's premise
for T5: retention must be proven **behaviourally** (write/query), never by asserting on
configuration output.

Behavioural proof, done as part of this spike on the same `spike_db` (1h retention):
wrote one point at `now − 2h` and one at `now − 5m`, queried both back immediately (no
wait for the background retention sweep, which logs `check_interval_seconds=1800`):

```
$ curl --data-binary "temp,src=spike value=1.0 <now-2h ns>
temp,src=spike value=2.0 <now-5m ns>" \
    "http://localhost:18181/api/v3/write_lp?db=spike_db&precision=nanosecond"
HTTP 204

$ curl -d '{"db":"spike_db","q":"SELECT * FROM temp ORDER BY time","format":"json"}' \
    http://localhost:18181/api/v3/query_sql
[{"src":"spike","time":"2026-08-31T18:26:56.633207200","value":2.0}]
```

Only the 5-minute-old point comes back. Retention is enforced **at query time**, not only
by the periodic background sweep — confirms ADR-0009/`MISTAKES.md` C-06's model (expired
points are filtered silently on read) and confirms T5's planned test will observe the
effect immediately with no sleep/wait needed.

## 6. Minimum flags for GitHub Actions

Same `serve` flags used above are all that's needed — no GPU, no special mounts, `file`
object store against the runner's local disk is sufficient (this spike used a named
Docker volume locally; a runner would use a plain bind path or another named volume, no
different in kind). Auth is on by default (no `--without-auth` needed or wanted — matches
ADR-0009's "auth enabled locally too" policy). Two extra findings relevant to T10 (CI) and
T2 (compose):

- **Auth is enforced on `/health` too** (401 without a token) — there is no built-in
  unauthenticated healthcheck endpoint on this build. T2's compose healthcheck either
  needs the bootstrapped token available to the healthcheck command, or must use
  `--disable-authz health` at `serve` time (flag exists — seen in `--help`, not
  exercised here since it changes the auth story and wasn't this spike's question).
- **`delete database` prompts for interactive confirmation by default** and will hang
  non-interactively unless run with `-y` / `--yes`. T5's throwaway-database teardown must
  pass `-y`, confirmed:
  ```
  $ docker exec influx-spike influxdb3 delete database --token "$TOKEN" -y spike_db
  Database "spike_db" deleted successfully
  ```

## Cleanup

Container, named volume and network created for this spike were all removed:

```
$ docker rm -f influx-spike
$ docker volume rm influx-spike-data
$ docker network rm dac-spike
```

`docker ps -a` / `docker volume ls` / `docker network ls` after cleanup show none of the
three remain (verified — output omitted, all three commands returned no matching rows).
Pulled images (`influxdb:latest`, `influxdb:3-core`, `influxdb:3.11.2-core`) were left in
the local image cache, since T2 needs `3.11.2-core` again immediately and re-pulling
buys nothing.

## Bottom line for Wave 1

- **Pin `influxdb:3.11.2-core`** in the compose file, not `latest` (which is currently
  2.x — ADR-0008's tag claim needs correcting) and not `3-core`/`3.11-core` (moving tags).
- **Token bootstrap works non-interactively**: `influxdb3 create token --admin`, called
  once against the running server; the script must treat a `409 token already exists`
  response as the no-op case, since the server itself gives no idempotent success path.
- `--retention-period` works and accepts `1h`/`Nd` style durations; retention is provably
  enforced at query time.
- `show databases` / configure API do not report retention on this build — T5 is right to
  test behaviourally.
- Two new implementation details for T2: no unauthenticated healthcheck path exists by
  default (needs a token or `--disable-authz health`); `delete database` needs `-y` for
  any non-interactive teardown (T5's fixture).

**No bounce required.** The mechanism works non-interactively; ADR-0008/0009's *policy*
(auth on locally, scripted bootstrap into a gitignored `.env`) stands. What needs
correcting is their factual claim about *how* the token appears (not automatic on first
boot — created by an explicit non-interactive command) and the `latest` tag assertion.
Both are handoff notes for T11, not architecture changes.
