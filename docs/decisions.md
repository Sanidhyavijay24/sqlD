# Architecture & Technical Decisions

## Decision 001: PostgreSQL 17 as Default Sandbox Container
- **Context:** The build plan specifies PostgreSQL 18 with HypoPG, or fallback to 17/16. PostgreSQL 17 is currently the stable release with reliable official Debian packages and pre-built HypoPG extensions (`postgresql-17-hypopg`).
- **Decision:** Use `postgres:17` as the default local sandbox base image (`sqldoctor-pg:17`). CI will matrix test against 18, 17, and 16.
- **Status:** Approved by user.

## Decision 002: Python Environment & Package Management
- **Context:** User engineering protocol mandates Conda environment with pinned `requirements.txt`.
- **Decision:** Active Conda environment `sqldoctor` (Python 3.12.16) used for execution, with dependencies tracked in `requirements.txt`.
- **Status:** Approved by user.

## Decision 003: Catalog-driven Schema Extraction over SQL Parsing
- **Context:** Parsing arbitrary PostgreSQL DDL via external AST parsers is fragile (custom types, domain constraints, vendor extensions).
- **Decision:** All user DDL is applied directly inside an ephemeral PostgreSQL schema/database, and schema metadata (`tables`, `columns`, `primary_keys`, `foreign_keys`, `unique_constraints`, `check_constraints`, `indexes`) is loaded directly from `pg_catalog` and `information_schema`.
- **Status:** In accordance with Build Plan Phase 0 specification.

## Decision 004: AST Engine & Dialect
- **Context:** AST analysis requires a permissive license (avoiding GPL `pglast`).
- **Decision:** Use `sqlglot` with `dialect="postgres"` for parsing, normalization, and AST mutation. PostgreSQL sandbox `PREPARE` / catalog validation serves as the final authority on syntactic and semantic validity.
- **Status:** In accordance with Build Plan Phase 0 specification.

## Decision 005: Dual Execution Engine (Postgres Sandbox & In-Memory SQLite Fallback)
- **Context:** Evaluation suites and CI require running hundreds of adversarial checks rapidly (sub-second) without requiring local Docker daemon to be active at every second of unit testing.
- **Decision:** `AdversaryVerifier` and `RandomVerifier` execute against the live PostgreSQL sandbox when `connection_uri` is provided, and fall back to an in-memory execution engine using type-affinity mapping when running offline.
- **Status:** Implemented in Phase 1 & 2. Zero false accepts on Trap Suite v1.

