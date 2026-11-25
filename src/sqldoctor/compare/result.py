"""
@file result.py
@description Result data structures and verdict enums for query comparison
@module sqldoctor/compare/result
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComparisonVerdict(StrEnum):
    """Verdict from comparing two query results."""

    EQUIVALENT = "equivalent"
    DIFFERENT = "different"
    UNVERIFIED = "unverified"


class ComparisonDetails(BaseModel):
    """Detailed evidence from a comparison check."""

    model_config = ConfigDict(extra="forbid")

    is_equivalent: bool = Field(description="Whether results match under comparison rules")
    verdict: ComparisonVerdict = Field(description="Standardized comparison verdict")
    reason: str = Field(description="Explanation of verdict or discrepancy")
    original_row_count: int = Field(description="Number of rows in original result")
    candidate_row_count: int = Field(description="Number of rows in candidate result")
    differences_count: int = Field(default=0, description="Count of unmatched or divergent rows")
    sample_diff: dict[str, Any] | None = Field(
        default=None, description="Sample row showing disparity between outputs"
    )
