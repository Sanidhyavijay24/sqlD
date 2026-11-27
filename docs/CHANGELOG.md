# Changelog

All notable changes to SQL Doctor (`sqld`) will be documented in this file.

## [0.8.0-phase9] - 2026-11-27

### Added
- **Open-Source Polish**:
  - Added Apache-2.0 `LICENSE`, GitHub Action PR SQL verifier (`.github/workflows/sql-verify.yml`), and animated terminal demo GIF (`docs/assets/demo.gif`) in `README.md`.
- **Workload Mode (`sqldoctor.workload`)**:
  - `parse_pg_stat_statements`: Parses JSON/CSV `pg_stat_statements` exports, filters non-optimizable statements, and ranks queries by `total_exec_time_ms`.
  - `consolidate_indexes`: Deduplicates and merges prefix-redundant `CREATE INDEX` proposals across multiple queries.
  - `HypoPGAdvisor`: Evaluates consolidated indexes across all top-$N$ workload queries using real `hypopg_create_index` + `EXPLAIN (FORMAT JSON)` when Docker PG17 is running (or deterministic offline fallback).
  - `WorkloadAnalyzer` & `sqld workload`: Diagnoses top-$N$ queries under a global USD budget and emits a consolidated `WorkloadReport`.
  - Added `examples/pg_stat_statements.json` and `tests/test_workload.py` (125/125 tests passing).


## [0.7.0-phase8] - 2026-11-27

### Added
- **Model Context Protocol (MCP) Server (`sqldoctor.mcp`)**:
  - Added strict Pydantic-validated MCP tool handlers (`verify_rewrite_tool`, `diagnose_query_tool`, `replay_receipt_tool`) with path-traversal guards in `sqldoctor.mcp.tools`.
  - Added FastMCP server (`sqldoctor.mcp.server`) supporting `stdio` and `sse` transports.
  - Added `sqld mcp [--transport stdio|sse]` CLI command and `mcp>=1.2.0,<2.0.0` dependency.
  - Added `tests/test_mcp.py` covering strict schema validation, path guards, receipt generation, and CLI help.


## [0.6.0-phase5] - 2026-11-25

### Added
- **Comprehensive Evaluation Suites (`eval/suites/`)**:
  - `trap_suite_v2.py`: 50 known-wrong SQL rewrites across NULL logic, outer-join conversions, multiset duplication, window frames, and subquery semantics.
  - `good_suite_v2.py`: 30 known-equivalent SQL rewrites.
  - `perf_suite.py`: 30 TPC-H-derived analytical and transactional benchmark queries.
- **Evaluation Orchestrator (`sqldoctor.eval.runner`)**:
  - Added `EvaluationRunner` comparing SQL Doctor against baselines (`LLM-as-judge`, `Fixed-Random Verifier`) and adversary ablations (`no_enum`, `no_fuzz`).
  - Added `sqld eval` CLI command generating `trap_results.json`, `good_results.json`, `perf_results.json`, and `summary_table.md`, enforcing the 0-false-accept release gate.
- **Packaging & Test Suite**:
  - Configured `pyproject.toml` and `EvaluationRunner` import paths so `sqld` and `pytest` resolve `eval/` directly from CLI entrypoints.
  - Added `tests/test_evaluation.py`; full suite passing at **117/117 tests**, `ruff` and `mypy` clean across 63 source files.


## [0.5.0-phase4] - 2026-11-24

### Added
- **Multi-Scale Benchmark Harness (`sqldoctor.bench`)**:
  - Implemented `BenchmarkRunner` executing `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` across multiple scales (e.g. 1,000 and 10,000 rows).
  - Primary metric: Shared buffer access count (`Shared Hit Blocks` + `Shared Read Blocks`).
  - Secondary metric: Median execution wall time (ms) with instability detection.
  - Interleaved repeated executions (default 7 repeats) with initial cache warm-up.
  - Detects and flags scale-dependent optimizations and volatile execution plans.
- **Self-Contained SQL Receipt Writer (`sqldoctor.receipt.writer`)**:
  - `ReceiptWriter` emits standalone `.sql` files with header comments (verdict, seed, tool version, timestamp), DDL statements, minimal counterexample `INSERT`s, CTE queries, and bidirectional multiset `EXCEPT ALL` comparison queries.
  - Self-contained and replayable directly in plain `psql` without installing SQL Doctor.
- **Receipt Replay Engine (`sqldoctor.receipt.replay`)**:
  - `ReceiptReplayer` parses and executes `receipt.sql` to verify verdict reproducibility.
  - Validates that recorded verdict reproduces (0 disparity rows for `TESTED_EQUIVALENT` / `NO_OP`, >0 disparity rows for `REJECTED`).
- **Static HTML Report Generator (`sqldoctor.report.generator`)**:
  - Zero-dependency, offline-ready single-file HTML report generator using Jinja2 templates.
  - Visualizes side-by-side query diff, color-coded verdict badge, minimal counterexample dataset table, benchmark buffer speedup table, and proposed indexes.
- **CLI Commands & Flags (`sqldoctor.cli`)**:
  - Added `sqld bench ORIGINAL CANDIDATE --schema schema.sql [--scales 1000,10000] [--repeats 7] [--json]`.
  - Added `sqld replay RECEIPT_PATH [--json]` (exit 0 on match, 1 on mismatch).
  - Added `--receipt <path>` and `--html <path>` options to `sqld verify` and `sqld diagnose`.
- **Phase 4 Gate Verification**:
  - Standalone receipts replay and confirm recorded verdicts.
  - Multi-scale benchmarks measure buffer speedups and wall-time percentiles.
  - Static HTML reports render with embedded CSS and zero external dependencies.
  - Full test suite passing at **112/112 tests**.


## [0.4.0-phase3] - 2026-11-24

### Added
- **LLM Client Adapter (`sqldoctor.agent.llm`)**:
  - OpenAI-compatible chat completion client with automatic provider detection (Google Gemini, OpenAI, Anthropic, Ollama, local models).
  - Deterministic SHA-256 prompt-hash response caching to disk (`cache/llm/<hash>.json`) ensuring 0-token, instant re-execution of repeated queries.
  - Per-run cumulative cost tracking and hard budget enforcement (`max_cost_usd`).
  - Automatic exponential backoff and retry on HTTP 429/503 capacity spikes.
- **PostgreSQL Plan Normalizer (`sqldoctor.agent.plan`)**:
  - Normalized plan parser stripping costs, timings, and volatile memory/buffer stats while preserving join tree and scan hierarchy.
  - Structural plan equivalence check to detect no-op rewrites that yield identical execution plans.
- **Agent Diagnostic Loop (`sqldoctor.agent.loop`)**:
  - `DiagnosticAgent` orchestrates conversational proposal generation, index recommendations, and adversary judgment.
  - Minimal counterexample datasets and disparity reasons flow back to the model for iterative refinement.
  - Safe text/markdown code-block extraction with full support for `CREATE INDEX` and `SELECT` rewrites.
- **CLI Command `sqld diagnose` (`sqldoctor.cli`)**:
  - Diagnoses queries: `sqld diagnose <query.sql> --schema <schema.sql> [--json]`.
  - Emits colored terminal output or standardized machine-readable JSON.
- **Phase 3 Gate Verification**:
  - 10 representative slow queries evaluated (5 equivalent rewrites + 5 subtle traps) with 100% verdict accuracy.
  - Verified 0-token cached execution on subsequent runs.
  - Test suite green at 104 passing tests across unit, integration, and adversary suites.


## [0.3.0-phase2] - 2026-11-24

### Added
- **Adversarial Small-Scope Enumerator (`sqldoctor.adversary.enumerator`)**:
  - Boundary value pool extraction from query AST literals ($c, c-1, c+1$, NULL, ties, strings).
  - Combinatorial generation of 0-row, 1-row, and 2-row relational datasets respecting constraints.
- **AST Mutation Engine (`sqldoctor.mutate.engine`)**:
  - Deterministic AST mutant generation via `sqlglot` covering 6 core mutation rules: `FlipComparison`, `ShiftConstant`, `SwapBoolean`, `ToggleDistinct`, `SwapAggregate`, and `DropPredicate`.
  - Mutation adequacy scoring evaluating the fraction of mutants killed by test datasets.
- **Delta-Debugging Counterexample Minimizer (`sqldoctor.adversary.minimizer`)**:
  - Minimizes bloated counterexample datasets down to 1-minimal separating rows.
- **Adversary Verifier Engine (`sqldoctor.verifier.adversary_verifier`)**:
  - Complete verification orchestrator combining small-scope enumeration, fuzzing, and mutation adequacy.
  - Emits standardized JSON verdict reports (`schema_version: 1`).
- **CLI Command `sqld verify` (`sqldoctor.cli`)**:
  - Standalone verification command without requiring LLM dependencies.
  - Supports `--schema`, `--seed`, and `--json` formatting.
  - Exits with 0 for accepted/tested_equivalent, 1 for rejected with counterexample, 2 for unverified, 3 for error.
- **Trap Suite v1 & Good Suite v1 (`eval/suites/`)**:
  - 25 trap cases across NULL logic, joins, aggregates, ordering ties, window frames, and operator precedence.
  - 15 good rewrite cases across constant folding, predicate simplification, identities, and commutativity.
  - Achieved **0 false accepts** on all 25 traps and **0 false rejects** on all 15 good cases.
  - Total test suite now at 95 passing unit and integration tests.

## [0.2.0-phase1] - 2026-11-24

### Added
- **Result Comparison Engine (`sqldoctor.compare.comparator`)**:
  - Implemented bag (multiset) multiset comparison semantics (`EXCEPT ALL` in both directions).
  - Implemented ordered list comparison when the original query AST specifies top-level `ORDER BY`.
  - Implemented `IS NOT DISTINCT FROM` equality semantics treating NULLs as equal.
  - Implemented numerical tolerance comparison for floating-point and decimal values (`rel_tol=1e-6`, `abs_tol=1e-9`).
  - Added volatile function detector returning `unverified` for unpinned queries.
- **Constraint-Aware Seeded Data Generator (`sqldoctor.datagen.generator`)**:
  - Deterministic PRNG seeding ensuring bit-for-bit reproducible dataset synthesis.
  - Topological sorting of relational tables via dependency graph (Kahn's algorithm).
  - Strict preservation of `NOT NULL`, `PRIMARY KEY`, single/composite `UNIQUE` constraints.
- **Fixed-Random-Data Verifier (`sqldoctor.verifier.random_verifier`)**:
  - 10 hand-crafted query pairs judged with 100% accuracy and strict determinism.

## [0.1.0-phase0] - 2026-11-24

### Added
- **Core Architecture & Layout**: Clean modular structure under `src/sqldoctor`.
- **PostgreSQL 17 Sandbox with HypoPG**: Dedicated Dockerfile bundling `postgresql-17-hypopg`.
- **Catalog-Driven Schema Extraction (`sqldoctor.schema.loader`)**: Direct extraction from `pg_catalog`.
- **AST Parsing and Normalization (`sqldoctor.sql.ast`)**: `sqlglot` engine for 20 sample queries round-trip.
- **CI Matrix (`.github/workflows/ci.yml`)**: GitHub Actions workflow testing matrix across PostgreSQL 16, 17, and 18.
