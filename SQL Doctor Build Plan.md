# SQL Doctor Build Plan

Nov 22, 2026 · @Sanidhya

SQL Doctor is an agentic tool that proposes PostgreSQL query rewrites and index changes, then lets deterministic machinery (sandbox, adversarial data, mutation testing, plan checks, benchmarks) decide whether to trust them, and ships a re-runnable receipt for every verdict.

## How to use this doc

This doc is the single source of truth for building SQL Doctor: the coding agent reads it once from top to bottom, then works one phase at a time from the Phased build section.

Working agreement for the coding agent:

1. Build one phase at a time. Do not start phase N+1 until the gate for phase N passes.
2. Every phase ends with green tests, a README demo command, a CHANGELOG entry, and a note in `docs/decisions.md` for every place the code deviates from this doc.
3. The LLM only proposes. Equivalence, performance and safety verdicts come from deterministic code with fixed seeds, never from a model's opinion.
4. In real-data mode the LLM never sees row values, only schema and aggregate statistics.
5. All execution happens in a throwaway Postgres container. Never write to a user's database.
6. If a spec choice looks wrong, build the simplest working version and record the issue in `docs/decisions.md`. Do not silently redesign.
7. Write tests before verdict logic. Every bug found later becomes a permanent trap-suite or regression case.
8. Pin dependency versions. Record seed, Postgres version, tool version and model name in every verdict.
9. Do not invent benchmark numbers. Any figure in the README, the receipts or the write-up must come from a run that is checked in under `eval/`.

The repo name `sqldoctor` and the CLI name `sqld` are working names (see Open decisions).

## Idea and positioning

SQL Doctor takes a slow PostgreSQL query plus its schema, asks an LLM for faster rewrites and indexes, and reports a rewrite as safe only if it survives a deterministic search for counterexamples. Every verdict ships with a receipt that re-runs in plain `psql`.

**The problem.** LLM-written rewrites are often wrong in subtle ways: NULL handling in `NOT IN`, duplicate rows after a join, empty groups, outer joins turned into inner joins, ties under `LIMIT`. Index and rewrite advisors either do not verify at all, or verify only a narrow SQL fragment with formal tools. Published work on LLM query rewriting reports that formal equivalence checkers struggle to verify LLM rewrites of realistic benchmark queries, so verification is the open, unsolved piece.

**The idea.** Split the work cleanly:

| Role | Who does it | Why |
| --- | --- | --- |
| Proposal | LLM agent | Creative, cheap to be wrong |
| Judgement | Sandbox, adversarial datasets, mutation testing, plan comparison | Deterministic, reproducible, auditable |
| Evidence | Receipt script and benchmark report | Anyone can re-run it without our tool |
| Honesty | Graded verdicts | Never claims more than it tested |

**Positioning line:** rewrites you can trust, with counterexample search, measured evidence and re-runnable receipts.

**Who uses it.** Backend developers with one slow query, DBAs reviewing LLM-suggested SQL, teams adopting coding agents that emit SQL, and researchers who want a verification baseline.

**Honest limits.** Equivalence of general SQL is undecidable, so the ceiling is bounded or empirical evidence, not proof. The strongest positive verdict is "tested-equivalent", and the docs, CLI output and README must say so.

**Name.** SQL Doctor is a working name only. Idera already sells a SQL Server product called SQL Doctor, so pick a different public name before launch.

## Scope and non-goals

The CV-minimum is phases 0 to 5 (about 7 to 8 weeks at 15 to 20 focused hours a week): a Postgres-only CLI that proposes rewrites, judges them with a counterexample search, measures them honestly, emits receipts, and is evaluated against baselines. Everything after phase 5 is optional and gated.

| Tier | Includes | Phases |
| --- | --- | --- |
| CV-minimum | Sandbox, data generation, adversary, mutation adequacy, graded verdicts, agent loop, benchmark, receipts, trap suite, baselines, ablations | 0 to 5 |
| Depth | Assumption ledger, hypothetical-index tuning | 6 |
| Reach | Real-data mode, MCP server, GitHub Action | 7 to 8 |
| Stretch | Workload mode, time-boxed attack mode, solver-backed bounded proofs | 9 to 11 |

**Non-goals for v1**

- No DBMS other than PostgreSQL.
- No auto-applying changes to a production database.
- No claim of formal proof outside the optional solver tier.
- No hosted service, accounts or multi-tenant UI. Output is the CLI, JSON, a receipt file and a static HTML report.
- No monitoring or dashboard product. This is a verifier with an agent in front, not a DBA suite.

**Cut rule.** If the schedule slips, drop phases from the end. Never drop the trap suite or the baselines: they are what make the project credible.

## Core concepts

Every candidate gets exactly one of five verdicts, and the CLI exit code and JSON carry it.

| Verdict | Meaning | Evidence attached |
| --- | --- | --- |
| `rejected` | A dataset exists where original and candidate return different results | Minimized, executed counterexample (DDL, rows, both outputs) |
| `no_op` | Normalized `EXPLAIN` plans are identical | Both plans |
| `tested_equivalent` | Every adversarial dataset agrees and every killable mutant was killed | Dataset counts, mutation score, seed |
| `conditionally_equivalent` | Equivalent only under a constraint the schema does not declare | Assumption ledger: constraint, check query, enforcing DDL |
| `unverified` | Could not judge: timeout, nondeterministic function, unsupported feature | Reason code |

**Result comparison.** Compare as bags (multisets) with `EXCEPT ALL` in both directions. Compare as ordered lists only when the original has a top-level `ORDER BY`, and treat ties as order-insensitive unless the `ORDER BY` is total. Use `IS NOT DISTINCT FROM` semantics so NULLs compare equal. Compare floats with a tolerance. Queries with `random()`, `now()` and similar volatile functions return `unverified` unless the user pins them.

**Adversary.** Three generators, all respecting declared constraints (types, `NOT NULL`, `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, `CHECK`):

1. Systematic small-scope enumeration: tables with 0, 1, 2 and 3 rows drawn from a small value pool built from the constants and boundaries in the query (c, c-1, c+1, NULL, duplicates, ties).
2. LLM-targeted construction: when a mutant survives, the agent is asked for a dataset that separates it, and the dataset is validated by code before use.
3. Random fuzz with seeded generators at larger sizes.

**Mutation adequacy** (in the style of XData). Generate deterministic AST mutants of the original query: flip comparison operators, shift constants by one, swap `AND` and `OR`, change join type, drop or add `DISTINCT`, change `UNION` to `UNION ALL`, swap `NOT IN` and `NOT EXISTS`, change aggregate function, drop a predicate. The dataset pool must kill every killable mutant. A surviving mutant is flagged as possibly equivalent and reported, so the user sees how well the tests covered the query's logic.

**Assumption ledger.** When a counterexample only works because it breaks a constraint the schema never declared (for example a NULL in `orders.customer_id`), do not just reject. Re-test under that constraint. If the candidate then passes, return `conditionally_equivalent` with the derived constraint, a check query that counts violating rows in the user's data, and the `ALTER TABLE` that would enforce it. Decompose the speedup into three timings: original, original with the constraint, and candidate with the constraint, so users see how much of the gain came from the constraint alone.

**Minimization.** Counterexamples are shrunk (drop rows, simplify values) until no smaller dataset still separates the two queries.

**Performance honesty.** Buffer counts from `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` are the primary metric and wall time is secondary. Use interleaved repeats, at least two data scales, and both common and rare parameter values. Report the speedup distribution, not one number. A candidate that is only faster at one scale or one parameter is flagged.

**Receipt.** A self-contained `.sql` file: header comments (verdict, seed, versions), DDL, the minimal dataset, both queries, and a comparison query. It runs with `psql -f receipt.sql` and needs no SQL Doctor install.

## Architecture and stack

&#91;embedded content: architecture · agent proposes, deterministic judge decides\]

The agent only ever produces candidates. Everything that decides a verdict runs in the deterministic judge, and counterexamples flow back to the agent so it can try again within its budget.

**Stack**

| Layer | Choice | Why |
| --- | --- | --- |
| Language and tooling | Python 3.12, `uv`, `ruff`, `mypy`, `pytest` | Fast to build, easy for contributors |
| CLI and models | Typer, Pydantic | Typed verdict and config schemas |
| Database driver | `psycopg` 3 | Native Postgres features, `COPY` for data loading |
| Sandbox | Docker image built from `postgres:18` plus the HypoPG package | Throwaway, reproducible, supports hypothetical indexes |
| SQL parsing and mutation | `sqlglot` with the Postgres dialect | Permissive license, easy AST edits. Postgres itself confirms validity (see licensing) |
| LLM access | Thin adapter over any OpenAI-compatible endpoint | Bring-your-own key, local models work, no vendor lock-in |
| Agent loop | Own small loop, no framework | Auditable, testable, easy to cache for reproducibility |
| Reports | Jinja templates, static HTML, no JS dependencies | Opens anywhere |
| CI | GitHub Actions matrix over Postgres 18, 17, 16 | Version support is tested, not claimed |

**Source layout:** `src/sqldoctor/` with modules `cli`, `sandbox`, `schema`, `datagen`, `compare`, `adversary`, `mutate`, `agent`, `bench`, `receipt`, `report`; plus `tests/`, `eval/` (suites and checked-in results) and `docs/`.

**Agent tools** (the only things the LLM can call): `get_schema`, `get_stats_summary`, `explain`, `verify_candidate`, `propose_index`, `run_benchmark`, `submit`. The LLM can never write a verdict. `submit` just ends the loop with the best verified candidate.

**Determinism rules.** Fixed seeds everywhere, no wall-clock in verdict logic, LLM responses cached by prompt hash in tests, and every verdict records the seed and versions.

## Interfaces: CLI, config, verdict and receipt

The `verify` command takes no LLM at all, so it is useful on its own, easy to test, and the thing the trap suite and the GitHub Action call.

| Command | What it does | Phase |
| --- | --- | --- |
| `sqld up` / `sqld down` | Start or stop the sandbox Postgres container | 0 |
| `sqld verify ORIGINAL CANDIDATE --schema schema.sql` | Judge one candidate with no LLM and print the verdict | 2 |
| `sqld diagnose query.sql --schema schema.sql` | Full agent loop: propose, verify, benchmark, report | 3 |
| `sqld bench ORIGINAL CANDIDATE` | Performance comparison only | 4 |
| `sqld replay receipt.sql` | Re-run a receipt and confirm the verdict | 4 |
| `sqld eval --suite traps\|good\|perf` | Run the evaluation suites | 5 |
| `sqld profile --dsn ...` | Local profiling of a real database | 7 |
| `sqld mcp` | Start the MCP server | 8 |

Exit codes: 0 accepted (`tested_equivalent`, `conditionally_equivalent` or an accepted `no_op`), 1 `rejected`, 2 `unverified`, 3 usage or environment error.

**Config** (`sqld.toml`):

```toml
[sandbox]
image = "sqldoctor-pg:18"
pg_version = 18
statement_timeout_ms = 10000

[adversary]
seed = 20261123
max_rows_per_table = 3
fuzz_datasets = 200
enumeration_cap = 5000

[agent]
provider = "openai-compatible"   # any OpenAI-compatible endpoint, including local models
model = "set-me"
max_proposals = 6
max_cost_usd = 1.00

[bench]
scales = [1000, 100000]
repeats = 7
interleave = true
```

**Verdict JSON** (`schema_version` bumps on any breaking change):

```json
{
  "schema_version": 1,
  "verdict": "conditionally_equivalent",
  "original_sha256": "...",
  "candidate_sha256": "...",
  "versions": {"tool": "0.1.0", "postgres": "18.x", "model": "..."},
  "seed": 20261123,
  "datasets": {"enumerated": 0, "targeted": 0, "fuzz": 0},
  "mutants": {"total": 0, "killed": 0, "survived_possibly_equivalent": []},
  "counterexample": null,
  "assumptions": [
    {
      "kind": "not_null",
      "target": "orders.customer_id",
      "check_sql": "SELECT count(*) FROM orders WHERE customer_id IS NULL",
      "enforce_ddl": "ALTER TABLE orders ALTER COLUMN customer_id SET NOT NULL"
    }
  ],
  "performance": {"metric": "shared_buffers_hit_plus_read", "scales": []}
}
```

**Receipt layout** (`receipt.sql`):

1. Header comments: verdict, seed, versions, one-line explanation.
2. `CREATE TABLE` statements and the minimal dataset as `INSERT`s.
3. The original query and the candidate as named views or CTEs.
4. A comparison query using `EXCEPT ALL` in both directions.
5. A trailing comment with the expected output, so a reader sees at once whether it reproduces.

## Phased build

&#91;embedded content: roadmap · phases 0 to 5 core, 6 to 11 optional\]

Build in order and stop at each gate. Estimates assume 15 to 20 focused hours a week; double them if you have fewer. After phase 5 you have a finished, evaluated project, and the evaluation results decide which optional phases are worth doing.

| Phase | Estimate | Gate (all must pass) | Kill or pivot rule |
| --- | --- | --- | --- |
| 0 Setup | 0.5 wk | `sqld up` starts the custom image with HypoPG; CI is green on Postgres 18, 17 and 16; schema loads from catalogs; `sqlglot` round-trips 20 sample queries | If the HypoPG image fails, defer index work to phase 6. If round-tripping fails often, use `PREPARE` in the sandbox for validity and keep a minimal normalizer |
| 1 Sandbox | 1 wk | Constraint-aware seeded data generator; comparison tests pass for bags, ordered results, NULLs and floats; 10 hand-written query pairs judged correctly with fixed random data | If results differ between identical runs, stop and fix determinism before going on |
| 2 Adversary | 1.5 wk | `sqld verify` rejects every trap case written so far (start with 25), does not reject the good cases (start with 15), reports a mutation score, and minimizes counterexamples | If enumeration explodes, cap the value pool and lean on targeted and fuzz data. If a trap class survives two redesigns, document it as a known limit and return `unverified` for that pattern |
| 3 Agent | 1 wk | `sqld diagnose` on 10 slow queries gives every candidate a verdict, enforces the cost cap, and reproduces from cached LLM responses | If proposals are poor, add rule-based rewrite hints to the prompt and narrow to common patterns |
| 4 Evidence | 1 wk | Every generated receipt replays in plain `psql` and reproduces its verdict; benchmark spread is reported; the HTML report renders | If timing is noisy, report buffers only and mark wall time as indicative |
| 5 Evaluation | 1.5 wk | Trap suite (about 50), good suite (about 30) and performance suite (about 30) run; baselines and ablations run; results checked in under `eval/`; zero false accepts on the trap suite | A false accept is fixed or documented as a known limit before any claim is made. If few rewrites win, report that honestly |
| 6 Depth | 1.5 wk | Ledger derives the right constraint in at least 10 hand-made cases (`NOT NULL`, `UNIQUE`, foreign key) with a working check query and DDL; speedup decomposition shown; hypothetical indexes confirmed by building the real index in the sandbox | If derivation is unreliable, restrict it to `NOT NULL` and `UNIQUE` |
| 7 Real-data | 1.5 wk | Profile and observed constraints work on a public sample dataset; a test inspects LLM payloads and finds no row values; read-only enforcement tested | If imported statistics do not reproduce plans, skip the twin and use read-only instance checks |
| 8 Integrations | 1 wk | MCP tools called from a coding agent in a demo; the Action comments a verdict on a sample repo's pull request | Drop whichever one is not clean |
| 9 Workload | 1.5 wk | Runs on a `pg_stat_statements` export of the performance suite and returns a consistent index set | Drop if time is short |
| 10 Attack | 2 wk box | One reproducible bug in a real SQL-generating tool, or a written negative result | Stop at 2 weeks regardless |
| 11 Bounded proofs | 2 wk max | `bounded_proved` on 20 select-project-join queries with k stated | Drop if it is not clean |

### What to build in each core phase

**Phase 0**

- Repo layout from the Architecture section, `uv`, `ruff`, `mypy`, `pytest`, pre-commit.
- Dockerfile for the sandbox image and a `sqld up` that starts it and waits for readiness.
- GitHub Actions matrix over Postgres versions.
- Schema loader: run the user's DDL in the sandbox, then read tables, columns, types and constraints from the Postgres catalogs into a typed internal model. The catalogs, not a parser, are the source of truth.

**Phase 1**

- Executor with per-run statement timeout. Use a template database so each dataset starts from a clean copy quickly.
- Constraint-aware seeded data generator: types, `NOT NULL`, `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, `CHECK`; load with `COPY`.
- Comparison module with the rules from Core concepts, with unit tests for each rule.
- The fixed-random-data verifier, kept as the first baseline for phase 5.

**Phase 2**

- Small-scope enumerator and value-pool builder from the query's constants.
- Mutation engine on the `sqlglot` AST with the mutant list from Core concepts, and a mutation score.
- Hook for LLM-targeted datasets, tested with fixture responses before any real model is used.
- Delta-debugging minimizer for counterexamples.
- `sqld verify`, trap suite v1 (25 cases) and good-rewrite suite v1 (15 cases).

**Phase 3**

- LLM adapter for OpenAI-compatible endpoints, with response caching keyed by prompt hash.
- Agent loop with the tools from Architecture, versioned prompt files, a proposal limit and a cost cap.
- Feedback of counterexamples and surviving mutants into the next proposal.
- No-op detection by comparing normalized `EXPLAIN` plans (drop costs and row estimates, keep node types, relations, conditions).
- `sqld diagnose`.

**Phase 4**

- Benchmark harness: `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, data at two scales, interleaved repeats, common and rare parameter values from a params file, a reported distribution.
- Receipt writer and `sqld replay`.
- Static HTML report with the diff, verdict, counterexample or ledger, and benchmark charts.
- README with a terminal recording of a wrong rewrite being rejected.

**Phase 5**

- Finish the three suites, the eval runner that writes `eval/results/*.json` and summary tables, the baselines, the ablation flags and the multi-model run.
- Write the evaluation write-up skeleton, tag `v0.1.0`, and decide which optional phases to do next.

Phases 6 to 11 are specified in Core concepts, Real-data mode and Integrations. Re-read those sections when you start each one.

## Evaluation and benchmark

The evaluation is what turns this from a demo into a result. It is built in phase 5 and re-run for every release. All numbers in the README come from checked-in runs under `eval/`; the figures below are targets, not results.

| Suite | Contents | Target |
| --- | --- | --- |
| Trap suite | About 50 known-wrong rewrites across the categories below | Zero false accepts |
| Good-rewrite suite | About 30 known-equivalent rewrites | Low false-reject rate, reported with the reasons |
| Performance suite | About 30 queries, including TPC-H-derived ones, with seeded data at two scales | Speedup distribution measured in buffers and wall time |
| Multi-model study | The same three suites with 3 to 4 different LLMs | Cost and success per verified win |

**Trap categories:** `NOT IN` versus `NOT EXISTS` with NULLs; `UNION` versus `UNION ALL`; removing or adding `DISTINCT`; joins to non-unique keys; `COUNT` over empty groups; outer join turned into inner join; predicate pushdown across an outer join; ties under `LIMIT` and `ORDER BY`; `DISTINCT ON`; window frame changes; integer division and rounding; case and collation; timestamp and timezone boundaries; `HAVING` versus `WHERE`; correlated subquery to join with duplicates.

**Baselines** the system must beat on the trap suite:

1. LLM-as-judge: ask a model whether the two queries are equivalent.
2. Fixed random data: run both queries on one random dataset and compare.
3. User sample data: run both on a small realistic sample.

**Ablations:** remove each of enumeration, mutation adequacy, LLM-targeted datasets and fuzz, and report what each one catches that the others miss.

**Reporting.** Publish a table of false accepts, false rejects and unverified rate per method, the per-category breakdown, and the list of every case where a method failed. Include a threats-to-validity section: the traps were written by us, so also run the system on rewrites produced by third-party tools or by models never used to design the traps.

## Real-data mode

Real-data mode lets someone point the tool at data they already have and get realistic verification and benchmarking without sending that data anywhere. It is phase 7, built only after the CV-minimum is done.

**Stages**

1. **Profile locally.** Row counts, null fractions, distinct counts and value ranges, read from `pg_stats` and cheap aggregates.
2. **Observed constraints.** Detect candidate `NOT NULL`, `UNIQUE` and foreign-key relationships that hold on this snapshot. Label every one "observed on this snapshot", never "guaranteed", and feed them to the assumption ledger as suggestions only.
3. **Instance checks.** Run the original and the candidate on a read-only copy and compare results on the real instance as extra evidence. This supplements the adversary, it does not replace it.
4. **Statistical twin (optional).** Generate synthetic data matching the profile for benchmarking, so realistic timings need no copy of the real rows.

**Privacy rules**

- The LLM sees schema and aggregate counts only. Most-common values, histogram bounds and min/max are data, so they are excluded by default and sent only with an explicit opt-in flag.
- Connect with a read-only role, set `default_transaction_read_only`, and use a `statement_timeout`.
- `EXPLAIN ANALYZE` executes the query, so run it only on a replica or restored copy, never by default on production.
- Everything stays local: no telemetry, and the receipt for a real-data run contains synthetic or minimized data only.

**To verify in phase 7.** PostgreSQL 18 added functions for exporting and importing optimizer statistics, which could let the sandbox reproduce production plans without the rows. Check what they cover and how plans still differ because of configuration and hardware before relying on them, and say so in the docs.

## Integrations, workload mode and attack mode

These are phases 8 to 11. Each is independent and gated, so build only the ones that earn their place.

**MCP server (phase 8).** `sqld mcp` exposes `verify_rewrite`, `diagnose_query` and `replay_receipt` as MCP tools. The pitch: any coding agent can get a verdict before it ships SQL. The server wraps the same library calls as the CLI and adds no logic of its own.

**GitHub Action (phase 8).** On a pull request that touches `.sql` files or migrations, run `sqld verify` on each changed query pair against the schema built from the migrations. Post a comment with the verdict and attach receipts. Fail the check on `rejected` and warn on `unverified`.

**Workload mode (phase 9).** Input is a `pg_stat_statements` export. Rank queries by total time, diagnose the top N under a global budget, and propose one consolidated index set. Check that a proposed index helps several queries and does not break others. Use HypoPG hypothetical indexes to compare plans before building anything, and verify the real gain in the sandbox.

**Attack mode (phase 10, time-boxed to 2 weeks).** Point the adversary at SQL-generating software such as text-to-SQL outputs, ORMs and query builders, looking for real bugs. Do not target the database engines themselves: that space is already crowded with published fuzzers (SQLancer++, Argus, FuzzySQL, Gungnir and others). Treat it as a lottery ticket. If the time box ends without a real, reproducible finding, stop and write up the negative result.

**Solver-backed bounded proofs (phase 11, optional).** For a restricted fragment (select-project-join with simple aggregates), encode both queries in SMT for tables up to k rows, in the style of VeriEQL, and add a verdict `bounded_proved` with k stated. Only attempt it after everything else ships. Keep it behind a flag and never claim it covers full SQL.

## After the code is done

The project is only a CV asset once other people can run it, see the evidence, and understand the result in two minutes. Do these in order.

**1. Hardening (about 1 week)**

- Run the whole suite on Postgres 18 and the two previous major versions, in CI.
- Fuzz the tool itself: random queries must never crash it, and unsupported SQL must return `unverified` with a reason.
- Pin every dependency, publish a `pip install` path and a single `docker run` path, and test both on a clean machine.
- Add a limits page: what it does not verify, with examples.

**2. Documentation and demo (about 1 week)**

- README in three parts: one animated terminal demo of a wrong rewrite getting rejected with its counterexample, a 5-minute quickstart, and the evaluation table.
- A `docs/` folder: concepts, verdict reference, receipt format, how to add a trap case, how to add a rewrite rule.
- A static HTML report example checked in, so people can see the output without installing.

**3. Launch (about 1 week)**

- One technical write-up: the problem, the design, the evaluation, the failures. Lead with the trap suite result and the honest limits.
- Post to Hacker News, r/PostgreSQL and the Postgres community channels, one at a time, and answer every question. Do not mass-post.
- Ask two or three people who run Postgres to try it on a real slow query and record what broke.

**4. Upstream validation (ongoing, careful)**

- Use the tool on real slow queries from open-source projects' issue trackers, and contribute a fix only where the improvement is clear and you can attach a receipt.
- Many open-source projects now restrict or require disclosure of AI-assisted pull requests. Read each project's contributing policy first, disclose AI assistance where required, keep diffs small, and include reproducible test evidence. Skip projects that ban it.

**5. Paper option**

If the evaluation shows a clear result, for example verification catching wrong rewrites that LLM-as-judge accepts, write a short workshop-style paper or an arXiv note. Decide this after the multi-model study, not before.

**6. CV and interview prep**

- Fill the CV bullets only from real eval numbers. Draft shape: *Built an agentic Postgres query optimizer where an LLM proposes rewrites and a deterministic counterexample search decides; rejected N of M wrong rewrites that an LLM judge accepted, with replayable receipts.*
- Prepare a 2-minute walkthrough and a 10-minute deep dive: why the LLM does not judge, how mutation adequacy works, what the verdicts do and do not guarantee, and the biggest bug the adversary found in your own code.
- Keep a list of three failures and what you changed because of them. Interviewers ask for these.

**7. Maintenance**

- Triage issues weekly for the first month. Turn every reported wrong verdict into a trap-suite or regression case before fixing it.
- Support new Postgres majors within a month of release, and re-run the evaluation for each tool release.

## Risks, licensing and open decisions

Four decisions need an answer from you; each has a default the coding agent will use until you say otherwise.

| Decision | Options | Default |
| --- | --- | --- |
| Public name | Keep SQL Doctor as a working name only; candidates `pgreceipt` or `sqltrial` (availability not checked) | Use `sqldoctor` / `sqld` internally, rename before launch |
| LLM provider | Provider-agnostic with bring-your-own key and any OpenAI-compatible or local endpoint | Provider-agnostic, no vendor lock-in |
| Postgres versions | Latest only, or latest plus two previous majors | Latest plus two previous (18, 17, 16) |
| Project license | MIT or Apache-2.0 (permissive) versus GPL | Apache-2.0, provided no GPL dependency is linked |

**Licensing and tooling checks**

- **pglast** is licensed GPL-3.0-or-later, per its [PyPI page](https://pypi.org/project/pglast). Depending on it would push the project toward GPL, so the default is to avoid it. Use `sqlglot` (believed MIT, confirm in phase 0) for parsing, AST mutation and normalization, and use Postgres itself as the final authority on whether SQL parses (`PREPARE` or `EXPLAIN` in the sandbox).
- **libpg\_query** is believed to be BSD-licensed, but this was not confirmed. Check its `LICENSE` file before using any binding built on it.
- **HypoPG** [1.4.3 supports PostgreSQL 19](https://www.postgresql.org/about/news/hypopg-143-is-out-3326/) among its versions, and Debian ships a [postgresql-18-hypopg package](https://packages.debian.org/sid/postgresql-18-hypopg). The official `postgres` image does not include HypoPG, so build a small custom image (`FROM postgres:18`, install the HypoPG package, `CREATE EXTENSION hypopg`) and test it in phase 0. Confirm HypoPG's license in its repository.
- **Name clash.** Idera sells a SQL Server product called SQL Doctor. Choose a new public name and check the package, domain and GitHub names before the launch.

**Main risks**

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Adversary misses a real difference | A wrong rewrite is accepted | Mutation adequacy, trap suite as a release gate, honest verdict names, report surviving mutants |
| Scope creep | CV-minimum never ships | Cut rule: drop phases from the end, gates and kill criteria per phase |
| LLM proposals rarely win | Boring demos | Curate the performance suite, include proposals from several models, report the failure rate honestly |
| Timings are noisy | Misleading speedups | Buffers first, interleaved repeats, two scales, flag unstable results |
| Someone ships the same idea first | Lower novelty | Ship the CV-minimum early, lean on the evaluation and receipts |
| Cost of LLM calls | Surprise bills | Per-run cost cap in config, cached proposals in tests, local-model support |

**Sources:** [pglast on PyPI](https://pypi.org/project/pglast) · [HypoPG 1.4.3 announcement](https://www.postgresql.org/about/news/hypopg-143-is-out-3326/) · [Debian postgresql-18-hypopg](https://packages.debian.org/sid/postgresql-18-hypopg)
