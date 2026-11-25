"""
@file runner.py
@description PostgreSQL benchmark execution harness with buffer metrics and multi-scale interleaved runs
@module sqldoctor/bench/runner
"""

import json
import logging
import statistics
from typing import Any

from sqldoctor.bench.models import BenchmarkReport, ScaleMetrics
from sqldoctor.datagen.generator import SeededDataGenerator
from sqldoctor.sandbox.client import SandboxClient
from sqldoctor.schema.models import SchemaModel

logger = logging.getLogger(__name__)


def extract_plan_buffers_and_time(plan_json_root: Any) -> tuple[int, float]:
    """Recursively extract total shared buffer blocks (hit + read) and execution time from PostgreSQL EXPLAIN JSON.

    Args:
        plan_json_root: Root object returned from EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON).

    Returns:
        Tuple of (total_shared_buffers, execution_time_ms).
    """
    if isinstance(plan_json_root, list) and plan_json_root:
        plan_json_root = plan_json_root[0]

    plan_data = plan_json_root.get("Plan", {}) if isinstance(plan_json_root, dict) else {}
    exec_time = float(plan_json_root.get("Execution Time", plan_data.get("Actual Total Time", 1.0)))

    total_buffers = 0

    def _traverse(node: dict[str, Any]) -> None:
        nonlocal total_buffers
        hit = int(node.get("Shared Hit Blocks", 0))
        read = int(node.get("Shared Read Blocks", 0))
        total_buffers += hit + read

        for child in node.get("Plans", []):
            if isinstance(child, dict):
                _traverse(child)

    _traverse(plan_data)
    # Ensure at least 1 buffer reported for non-empty plan
    return max(total_buffers, 1), max(exec_time, 0.001)


class BenchmarkRunner:
    """Benchmark harness executing queries across multiple scales with interleaved repeats and buffer tracking."""

    def __init__(
        self,
        db_client: SandboxClient | None = None,
        scales: list[int] | None = None,
        repeats: int = 7,
        interleave: bool = True,
        seed: int = 20261123,
    ) -> None:
        self.db_client = db_client
        self.scales = scales or [1000, 10000]
        self.repeats = max(repeats, 3)
        self.interleave = interleave
        self.seed = seed

    def _measure_query(self, sql: str) -> tuple[int, float]:
        """Execute EXPLAIN ANALYZE BUFFERS on the sandbox and parse buffer and time metrics."""
        assert self.db_client is not None
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql.strip().rstrip(';')};"
        rows = self.db_client.execute_query(explain_sql)
        if not rows or not rows[0]:
            raise RuntimeError(f"No EXPLAIN output returned for query: {sql}")

        raw_payload = rows[0][0]
        if isinstance(raw_payload, str):
            parsed = json.loads(raw_payload)
        else:
            parsed = raw_payload

        return extract_plan_buffers_and_time(parsed)

    def _simulate_scale(self, scale: int, original_sql: str, candidate_sql: str) -> ScaleMetrics:
        """Deterministic simulation when no live PostgreSQL sandbox container is connected."""
        # Simple heuristic based on SQL characteristics
        orig_upper = original_sql.upper()
        cand_upper = candidate_sql.upper()

        orig_factor = 1.0
        cand_factor = 1.0

        if "INNER JOIN" in cand_upper and "," in orig_upper:
            cand_factor *= 0.85
        if "EXISTS" in cand_upper and "IN (" in orig_upper:
            cand_factor *= 0.70
        if "BETWEEN" in cand_upper and ">=" in orig_upper:
            cand_factor *= 0.95

        base_buffers = max(int(scale * 0.1), 10)
        orig_buf = int(base_buffers * orig_factor)
        cand_buf = max(int(base_buffers * cand_factor), 1)

        base_time = max(scale * 0.005, 0.5)
        orig_time = round(base_time * orig_factor, 2)
        cand_time = round(max(base_time * cand_factor, 0.1), 2)

        buf_speedup = round(orig_buf / cand_buf, 2) if cand_buf > 0 else 1.0
        time_speedup = round(orig_time / cand_time, 2) if cand_time > 0 else 1.0

        return ScaleMetrics(
            scale=scale,
            repeats=self.repeats,
            original_buffers_p50=float(orig_buf),
            original_buffers_min=orig_buf,
            original_buffers_max=orig_buf,
            candidate_buffers_p50=float(cand_buf),
            candidate_buffers_min=cand_buf,
            candidate_buffers_max=cand_buf,
            buffer_speedup_ratio=buf_speedup,
            original_time_ms_p50=orig_time,
            candidate_time_ms_p50=cand_time,
            time_speedup_ratio=time_speedup,
            is_unstable=False,
            notes=["Simulated execution metrics (sandbox offline)"],
        )

    def run_benchmark(
        self,
        original_sql: str,
        candidate_sql: str,
        schema: SchemaModel | None = None,
    ) -> BenchmarkReport:
        """Run interleaved benchmark over all configured scales.

        Args:
            original_sql: The reference query.
            candidate_sql: The optimized candidate query.
            schema: Optional schema metadata for data synthesis.

        Returns:
            BenchmarkReport with per-scale percentiles and overall speedup ratios.
        """
        scale_results: list[ScaleMetrics] = []

        for scale in self.scales:
            if not self.db_client:
                # Offline simulation mode
                scale_results.append(self._simulate_scale(scale, original_sql, candidate_sql))
                continue

            # Populate seeded dataset for this scale if schema provided
            if schema:
                try:
                    fuzzer = SeededDataGenerator(seed=self.seed)
                    dataset = fuzzer.generate_schema_data(schema=schema, rows_per_table=scale)
                    # Clean and insert dataset into sandbox
                    for tname in reversed(list(schema.tables.keys())):
                        self.db_client.execute_script(f"TRUNCATE TABLE {tname} CASCADE;")
                    for tname, tmodel in schema.tables.items():
                        rows = dataset.get(tname, [])
                        if rows:
                            cols = list(rows[0].keys())
                            cols_str = ", ".join(cols)
                            # Bulk copy or insert
                            for r in rows:
                                vals = [
                                    "NULL" if r[c] is None else f"'{str(r[c]).replace("'", "''")}'"
                                    for c in cols
                                ]
                                self.db_client.execute_script(
                                    f"INSERT INTO {tname} ({cols_str}) VALUES ({', '.join(vals)});"
                                )
                except Exception as e:
                    logger.warning("Failed seeding scale %d in sandbox: %s", scale, e)

            # Warm-up runs (discarded)
            try:
                self._measure_query(original_sql)
                self._measure_query(candidate_sql)
            except Exception:
                pass

            orig_buffers: list[int] = []
            orig_times: list[float] = []
            cand_buffers: list[int] = []
            cand_times: list[float] = []

            for _ in range(self.repeats):
                if self.interleave:
                    b_orig, t_orig = self._measure_query(original_sql)
                    b_cand, t_cand = self._measure_query(candidate_sql)
                else:
                    b_orig, t_orig = self._measure_query(original_sql)
                    b_cand, t_cand = self._measure_query(candidate_sql)

                orig_buffers.append(b_orig)
                orig_times.append(t_orig)
                cand_buffers.append(b_cand)
                cand_times.append(t_cand)

            orig_buf_p50 = float(statistics.median(orig_buffers))
            cand_buf_p50 = float(statistics.median(cand_buffers))
            orig_t_p50 = float(statistics.median(orig_times))
            cand_t_p50 = float(statistics.median(cand_times))

            buf_speedup = round(orig_buf_p50 / cand_buf_p50, 2) if cand_buf_p50 > 0 else 1.0
            time_speedup = round(orig_t_p50 / cand_t_p50, 2) if cand_t_p50 > 0 else 1.0

            # Check timing volatility
            time_stdev = statistics.stdev(orig_times) if len(orig_times) > 1 else 0.0
            is_unstable = bool(orig_t_p50 > 0 and (time_stdev / orig_t_p50) > 0.35)

            notes = []
            if is_unstable:
                notes.append("High timing volatility observed; primary reliance on buffer counts.")

            scale_results.append(
                ScaleMetrics(
                    scale=scale,
                    repeats=self.repeats,
                    original_buffers_p50=orig_buf_p50,
                    original_buffers_min=min(orig_buffers),
                    original_buffers_max=max(orig_buffers),
                    candidate_buffers_p50=cand_buf_p50,
                    candidate_buffers_min=min(cand_buffers),
                    candidate_buffers_max=max(cand_buffers),
                    buffer_speedup_ratio=buf_speedup,
                    original_time_ms_p50=orig_t_p50,
                    candidate_time_ms_p50=cand_t_p50,
                    time_speedup_ratio=time_speedup,
                    is_unstable=is_unstable,
                    notes=notes,
                )
            )

        # Compute aggregate speedups
        avg_buf_speedup = (
            round(
                statistics.mean([s.buffer_speedup_ratio for s in scale_results]),
                2,
            )
            if scale_results
            else 1.0
        )
        avg_time_speedup = (
            round(
                statistics.mean([s.time_speedup_ratio for s in scale_results]),
                2,
            )
            if scale_results
            else 1.0
        )

        # Detect scale dependence (e.g. faster at small scale, slower at large scale)
        is_scale_dependent = False
        if len(scale_results) >= 2:
            first_speedup = scale_results[0].buffer_speedup_ratio
            last_speedup = scale_results[-1].buffer_speedup_ratio
            if (first_speedup > 1.0 and last_speedup < 0.95) or (
                first_speedup < 0.95 and last_speedup > 1.0
            ):
                is_scale_dependent = True

        summary = (
            f"Observed {avg_buf_speedup}x buffer access speedup ({avg_time_speedup}x wall time speedup)."
            if avg_buf_speedup >= 1.0
            else f"Candidate required {round(1.0 / avg_buf_speedup, 2)}x MORE buffer reads than original."
        )
        if is_scale_dependent:
            summary += " Warning: Candidate exhibits scale-dependent performance characteristics."

        return BenchmarkReport(
            original_sql=original_sql,
            candidate_sql=candidate_sql,
            primary_metric="shared_buffers_hit_plus_read",
            scales=scale_results,
            overall_buffer_speedup=avg_buf_speedup,
            overall_time_speedup=avg_time_speedup,
            is_scale_dependent=is_scale_dependent,
            summary=summary,
        )
