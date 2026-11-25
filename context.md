# Context: SQL Doctor (`sqld`) Single Source of Truth

## 1. Project Overview
- **Name:** SQL Doctor (CLI: `sqld`)
- **Mission:** Production-grade agentic PostgreSQL query optimizer and deterministic verification engine. LLM agents propose rewrites and index candidates; deterministic machinery (disposable container, constraint-aware data generator, small-scope enumeration, AST mutation testing, bag equivalence checking, counterexample minimizer) decides verdicts with re-runnable receipts.
- **Current Phase:** Phase 5 (Completed - CV-Minimum Milestone Achieved, 117/117 tests passing, ruff & mypy clean)

## 2. Tech Stack
- **Python Version:** 3.12.16 (Conda env `sqldoctor`)
- **Package Management:** `pip` within Conda env, tracked in `requirements.txt`
- **Database:** PostgreSQL 17 (official Debian base image with HypoPG extension)
- **Containerization:** Docker (`sqldoctor-pg:17`)
- **Key Libraries:** `pydantic` (v2, strict validation `extra="forbid"`), `typer` (CLI), `psycopg` (v3, native binary protocol), `sqlglot` (Postgres dialect AST), `docker` (Python SDK), `jinja2` (reports), `pytest` (testing), `ruff` (linter/formatter), `mypy` (type checking).

## 3. Architecture & Directory Layout
```
c:\Codes\ideas\sqld/
├── .github/workflows/ci.yml       # CI matrix across Postgres 16, 17, 18
├── docker/
│   └── Dockerfile                 # PostgreSQL 17 + HypoPG sandbox image
├── docs/
│   └── decisions.md               # Architectural decision records
├── src/
│   └── sqldoctor/
│       ├── __init__.py
│       ├── config.py              # Pydantic-validated TOML/env configuration
│       ├── cli.py                 # Typer CLI application (sqld)
│       ├── bench/
│       │   ├── __init__.py
│       │   ├── models.py              # ScaleMetrics & BenchmarkReport models
│       │   └── runner.py              # Multi-scale interleaved benchmark harness
│       ├── eval/
│       │   ├── __init__.py
│       │   └── runner.py              # Comprehensive evaluation orchestrator & report generator
│       ├── receipt/
│       │   ├── __init__.py
│       │   ├── writer.py              # Standalone self-contained receipt.sql generator
│       │   └── replay.py              # Receipt replay & verdict confirmation engine
│       ├── report/
│       │   ├── __init__.py
│       │   ├── generator.py           # Static HTML report generator via Jinja2
│       │   └── templates/
│       │       └── report.html.j2     # Zero-dependency offline HTML report template
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── llm.py                 # LLM client with prompt caching & cost caps
│       │   ├── plan.py                # PostgreSQL EXPLAIN normalizer & no-op detector
│       │   ├── loop.py                # DiagnosticAgent loop & counterexample feedback
│       │   └── prompts/
│       │       └── diagnose_v1.txt    # Versioned system prompt
│       ├── adversary/
│       │   ├── constants.py           # AST constant extraction & value pooling
│       │   ├── enumerator.py          # Small-scope tuple enumerator
│       │   ├── minimizer.py           # Delta-debugging counterexample minimizer
│       │   └── targeted.py            # Targeted boundary condition hooks
│       ├── compare/
│       │   ├── comparator.py          # Multiset bag and ordered equality engine
│       │   └── result.py              # Comparison verdict models
│       ├── datagen/
│       │   └── generator.py           # Constraint-aware seeded data generator
│       ├── mutate/
│       │   ├── engine.py              # AST mutation engine & mutant generation
│       │   └── models.py              # Mutation scores and mutant representations
│       ├── verifier/
│       │   ├── adversary_verifier.py  # Full deterministic adversary verifier
│       │   └── random_verifier.py     # Fixed-random baseline verifier
│       ├── sandbox/
│       │   ├── __init__.py
│       │   ├── manager.py             # Docker container lifecycle (up, down, wait_ready)
│       │   ├── client.py              # Psycopg connection pool & statement execution
│       │   └── template.py            # Fast database template cloning
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── models.py              # Strict Pydantic models for tables, columns, constraints
│       │   └── loader.py              # pg_catalog metadata query engine
│       └── sql/
│           ├── __init__.py
│           └── ast.py                 # sqlglot wrapper, normalization & AST round-tripping
├── eval/
│   ├── __init__.py
│   ├── results/                   # Generated evaluation artifacts (JSON & Markdown)
│   │   ├── trap_results.json
│   │   ├── good_results.json
│   │   ├── perf_results.json
│   │   └── summary_table.md
│   └── suites/
│       ├── trap_suite_v2.py       # 50 comprehensive known-wrong SQL rewrites
│       ├── good_suite_v2.py       # 30 known-equivalent SQL rewrites
│       └── perf_suite.py          # 30 TPC-H-derived analytical & OLTP queries
├── tests/
│   ├── conftest.py                    # Shared fixtures & test database helpers
│   ├── test_agent.py                  # LLM caching, plan normalizer, agent loop tests
│   ├── test_bench.py                  # Benchmark harness & buffer metrics tests
│   ├── test_cli.py                    # CLI commands (up, down, --help) tests
│   ├── test_compare.py                # Comparison rules unit tests
│   ├── test_datagen.py                # Seeded constraint-aware datagen tests
│   ├── test_diagnose.py               # sqld diagnose CLI tests & Phase 3 gate (10 queries)
│   ├── test_good_suite.py             # Good rewrites suite (15 cases) tests
│   ├── test_minimizer.py              # Delta-debugging minimization tests
│   ├── test_mutator.py                # AST mutation & adequacy score tests
│   ├── test_pairs.py                  # Phase 1 gate tests (10 hand-written pairs)
│   ├── test_receipt.py                # Standalone receipt writer & replay engine tests
│   ├── test_report.py                 # Static HTML report generator & CLI flag tests
│   ├── test_roundtrip.py              # 20 complex query round-trip tests
│   ├── test_sandbox.py                # Container management & connection tests
│   ├── test_schema_loader.py          # pg_catalog schema extraction unit tests
│   └── test_trap_suite.py             # Trap suite (25 cases) tests
├── context.md                     # Single Source of Truth
├── requirements.txt               # Pinned dependencies
├── sqld.toml                      # Runtime configuration
└── .env.example                   # Environment variable template
```

## 4. Feature Status Checklist
- [x] Phase 0 - Foundation setup: requirements.txt, .gitignore, sqld.toml, decisions.md, context.md
- [x] Phase 0 - Dockerfile for PostgreSQL 17 + HypoPG extension
- [x] Phase 0 - Sandbox container manager (`sqld up`, `sqld down`, readiness polling)
- [x] Phase 0 - Schema catalog loader from `pg_catalog` & `information_schema`
- [x] Phase 0 - SQL AST round-tripping (20 sample queries via `sqlglot`)
- [x] Phase 0 - Typer CLI commands (`sqld up`, `sqld down`, `--version`)
- [x] Phase 0 - GitHub Actions CI matrix (PG 16, 17, 18)
- [x] Phase 0 - Gate verification & all unit tests green (28/28 tests passing, ruff & mypy clean)
- [x] Phase 1 - Sandbox executor, seeded constraint-aware datagen, bag comparator
- [x] Phase 1 - Comparison module (multiset bags, ordered lists, NULLs, float tolerance, volatile detection)
- [x] Phase 1 - Constraint-aware seeded generator (topological sort, PK, FK, NOT NULL, UNIQUE, COPY format)
- [x] Phase 1 - Template database manager for instant per-test cloning
- [x] Phase 1 - Fixed-random verifier (Phase 1 engine & Phase 5 Baseline 2)
- [x] Phase 1 - Gate verification (10 hand-written pairs judged, strict determinism, 50/50 tests green)
- [x] Phase 2 - Adversary small-scope enumerator from query constants (0, 1, 2, 3 rows)
- [x] Phase 2 - AST mutation engine (`sqlglot`) with 6 mutation rules & adequacy score
- [x] Phase 2 - Delta-debugging counterexample minimizer
- [x] Phase 2 - `sqld verify` CLI command with exit codes 0/1/2/3 and JSON report
- [x] Phase 2 - Trap suite v1 (25 cases) with 0 false accepts
- [x] Phase 2 - Good rewrite suite v1 (15 cases) with 0 false rejects
- [x] Phase 2 - Gate verification & all unit tests green (95/95 tests passing, ruff & mypy clean)
- [x] Phase 3 - LLM adapter, prompt caching, agent loop, `sqld diagnose`
- [x] Phase 3 - Deterministic SHA-256 prompt-hash response caching in `cache/llm/`
- [x] Phase 3 - Normalized PostgreSQL EXPLAIN plan comparison & no-op detection
- [x] Phase 3 - Counterexample feedback loop and surviving mutant reporting
- [x] Phase 3 - `sqld diagnose` CLI command with exit codes 0/1/2/3 and `--json`
- [x] Phase 3 - Gate verification (10 slow queries evaluated, 104/104 tests green, ruff & mypy clean)
- [x] Phase 4 - Benchmarking harness, receipt generator, static HTML reports
- [x] Phase 4 - `sqld bench` with buffer metrics (shared hit + read) & wall-time percentiles across scales
- [x] Phase 4 - Self-contained `receipt.sql` standalone format replayable in plain psql
- [x] Phase 4 - `sqld replay` command validating receipt verdict reproduction (exit 0/1)
- [x] Phase 4 - Zero-dependency offline static HTML report generator via Jinja2
- [x] Phase 4 - Gate verification (receipts replay, benchmark spread reported, 112/112 tests green)
- [x] Phase 5 - Evaluation runner, trap suite (50), good suite (30), perf suite (30)
- [x] Phase 5 - Baselines & Ablations (LLM-as-judge, fixed-random verifier, no_enum, no_fuzz)
- [x] Phase 5 - `sqld eval` CLI command with JSON outputs & Markdown summary table
- [x] Phase 5 - Gate verification: 0 false accepts across 50 traps (100% detection rate), 117/117 tests passing, ruff & mypy clean

## 5. Data Models (Strict Pydantic)
- `ColumnModel`: name, data_type, is_nullable, column_default, character_maximum_length, numeric_precision, numeric_scale.
- `ConstraintModel`: constraint_name, constraint_type (`PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK`), columns, foreign_table, foreign_columns, check_clause.
- `TableModel`: table_name, schema_name, columns, constraints, primary_key, foreign_keys, unique_constraints, check_constraints.
- `SchemaModel`: tables dict, custom types, indexes.
- `SandboxConfig`: image, pg_version, port, user, password, database, statement_timeout_ms.

## 6. API & CLI Contracts
- `sqld --help`: List available commands and global flags.
- `sqld up [--port PORT] [--detach]`: Build/start sandbox container and await readiness on localhost:PORT.
- `sqld down`: Stop and remove sandbox container.
- `sqld verify ORIGINAL CANDIDATE --schema schema.sql [--seed SEED] [--receipt receipt.sql] [--html report.html] [--json]`: Deterministically verify rewrite pair with adversary without LLM.
- `sqld diagnose QUERY --schema schema.sql [--config sqld.toml] [--receipt receipt.sql] [--html report.html] [--json]`: Full agent loop proposing rewrites and index candidates with deterministic verification and prompt-hash caching.
- `sqld bench ORIGINAL CANDIDATE --schema schema.sql [--scales 1000,10000] [--repeats 7] [--json]`: Performance comparison using buffer metrics (shared hits + reads) and wall time.
- `sqld replay RECEIPT_PATH [--json]`: Execute standalone receipt.sql and verify verdict reproducibility.
- `sqld eval [--suite traps|good|perf|all] [--baselines/--no-baselines] [--ablations/--no-ablations] [--out-dir eval/results] [--json]`: Execute comprehensive evaluation suite across baselines and ablations, enforcing the 0-false-accept release gate.
- Exit Codes: 0 on success (tested_equivalent, conditionally_equivalent, no_op, or replay verified), 1 on test rejection / replay mismatch / gate failure, 2 on unverified, 3 on environment/runtime error.

## 7. Technical Debt & Notes
- None. Fresh greenfield implementation conforming to Phase 0 requirements.
