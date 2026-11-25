"""
@file models.py
@description Strict Pydantic models for performance benchmarks and buffer metrics
@module sqldoctor/bench/models
"""

from pydantic import BaseModel, ConfigDict, Field


class ScaleMetrics(BaseModel):
    """Execution metrics collected at a single data scale."""

    model_config = ConfigDict(extra="forbid")

    scale: int = Field(description="Data scale (row count)")
    repeats: int = Field(description="Number of repeats executed")

    # Buffer access metrics (shared_hit + shared_read)
    original_buffers_p50: float = Field(description="Median buffer count for original")
    original_buffers_min: int = Field(description="Minimum buffer count for original")
    original_buffers_max: int = Field(description="Maximum buffer count for original")

    candidate_buffers_p50: float = Field(description="Median buffer count for candidate")
    candidate_buffers_min: int = Field(description="Minimum buffer count for candidate")
    candidate_buffers_max: int = Field(description="Maximum buffer count for candidate")

    buffer_speedup_ratio: float = Field(
        description="original_buffers_p50 / candidate_buffers_p50 (> 1.0 indicates improvement)"
    )

    # Wall time metrics (milliseconds)
    original_time_ms_p50: float = Field(description="Median execution time for original (ms)")
    candidate_time_ms_p50: float = Field(description="Median execution time for candidate (ms)")
    time_speedup_ratio: float = Field(
        description="original_time_ms_p50 / candidate_time_ms_p50 (> 1.0 indicates speedup)"
    )

    is_unstable: bool = Field(
        default=False, description="Flag indicating volatile timing or buffer variations"
    )
    notes: list[str] = Field(default_factory=list, description="Observations and flags")


class BenchmarkReport(BaseModel):
    """Comprehensive performance benchmark report across multiple scales."""

    model_config = ConfigDict(extra="forbid")

    original_sql: str
    candidate_sql: str
    primary_metric: str = Field(
        default="shared_buffers_hit_plus_read",
        description="Primary performance metric used for comparisons",
    )
    scales: list[ScaleMetrics] = Field(default_factory=list)
    overall_buffer_speedup: float = Field(
        default=1.0, description="Aggregate median buffer speedup across all scales"
    )
    overall_time_speedup: float = Field(
        default=1.0, description="Aggregate median wall-time speedup across all scales"
    )
    is_scale_dependent: bool = Field(
        default=False,
        description="True if candidate is only faster at certain scales and slower at others",
    )
    summary: str = Field(default="", description="Summary recommendation and interpretation")
