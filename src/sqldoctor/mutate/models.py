"""
@file models.py
@description Data models for AST mutations and mutation adequacy scoring
@module sqldoctor/mutate/models
"""

from pydantic import BaseModel, ConfigDict, Field


class Mutant(BaseModel):
    """An individual AST mutant generated from a query."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique mutant identifier")
    rule_name: str = Field(description="Name of mutation rule applied")
    description: str = Field(description="Human-readable explanation of mutation")
    original_sql: str = Field(description="Original SQL before mutation")
    mutated_sql: str = Field(description="Mutated SQL expression")
    is_killed: bool = Field(
        default=False, description="Whether a dataset produced differing results"
    )
    killing_dataset_id: str | None = Field(
        default=None, description="Identifier of dataset that killed mutant"
    )


class MutationScore(BaseModel):
    """Adequacy metrics evaluating whether test datasets exercise query logic branches."""

    model_config = ConfigDict(extra="forbid")

    total_mutants: int = Field(description="Total killable mutants generated")
    killed_mutants: int = Field(description="Number of mutants successfully killed")
    survived_mutants: int = Field(description="Number of surviving mutants")
    score: float = Field(description="Ratio of killed mutants to total (0.0 to 1.0)")
    survived_descriptions: list[str] = Field(
        default_factory=list, description="Descriptions of surviving mutants"
    )
