"""
@file models.py
@description Strict Pydantic models representing PostgreSQL schema objects
@module sqldoctor/schema/models
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConstraintType(StrEnum):
    """PostgreSQL table constraint types."""

    PRIMARY_KEY = "PRIMARY KEY"
    FOREIGN_KEY = "FOREIGN KEY"
    UNIQUE = "UNIQUE"
    CHECK = "CHECK"


class ColumnModel(BaseModel):
    """Metadata describing a single table column."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Column name")
    data_type: str = Field(description="PostgreSQL data type (e.g. integer, text, timestamptz)")
    is_nullable: bool = Field(default=True, description="Whether the column permits NULL values")
    column_default: str | None = Field(default=None, description="Default expression or value")
    character_maximum_length: int | None = Field(
        default=None, description="Max character length for varchar/char"
    )
    numeric_precision: int | None = Field(default=None, description="Precision for numeric types")
    numeric_scale: int | None = Field(default=None, description="Scale for numeric types")


class ConstraintModel(BaseModel):
    """Metadata describing a table constraint."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Constraint identifier")
    type: ConstraintType = Field(description="Type of constraint")
    columns: list[str] = Field(
        default_factory=list, description="Target column names on this table"
    )
    foreign_table: str | None = Field(
        default=None, description="Referenced table name for foreign keys"
    )
    foreign_columns: list[str] = Field(
        default_factory=list, description="Referenced column names for foreign keys"
    )
    check_clause: str | None = Field(
        default=None, description="Raw expression string for CHECK constraints"
    )


class IndexModel(BaseModel):
    """Metadata describing a table index."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Index name")
    columns: list[str] = Field(default_factory=list, description="Indexed column names")
    is_unique: bool = Field(default=False, description="Whether index enforces uniqueness")
    is_primary: bool = Field(default=False, description="Whether index backs a primary key")
    method: str = Field(default="btree", description="Index method (btree, hash, gin, gist)")
    definition: str | None = Field(default=None, description="Full DDL definition of the index")


class TableModel(BaseModel):
    """Metadata describing a complete database table."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Table name")
    schema_name: str = Field(default="public", description="PostgreSQL schema name")
    columns: dict[str, ColumnModel] = Field(
        default_factory=dict, description="Map of column name to ColumnModel"
    )
    constraints: list[ConstraintModel] = Field(
        default_factory=list, description="All declared table constraints"
    )
    indexes: list[IndexModel] = Field(
        default_factory=list, description="All declared table indexes"
    )

    @property
    def primary_key_columns(self) -> list[str]:
        """Return column names forming the primary key."""
        for c in self.constraints:
            if c.type == ConstraintType.PRIMARY_KEY:
                return c.columns
        return []

    @property
    def foreign_keys(self) -> list[ConstraintModel]:
        """Return all foreign key constraints."""
        return [c for c in self.constraints if c.type == ConstraintType.FOREIGN_KEY]

    @property
    def unique_constraints(self) -> list[ConstraintModel]:
        """Return all unique constraints."""
        return [c for c in self.constraints if c.type == ConstraintType.UNIQUE]

    @property
    def check_constraints(self) -> list[ConstraintModel]:
        """Return all check constraints."""
        return [c for c in self.constraints if c.type == ConstraintType.CHECK]


class SchemaModel(BaseModel):
    """Metadata describing a full database schema."""

    model_config = ConfigDict(extra="forbid")

    tables: dict[str, TableModel] = Field(
        default_factory=dict, description="Map of table name to TableModel"
    )

    def get_table(self, name: str) -> TableModel | None:
        """Fetch table model by name (case-insensitive lookup)."""
        lower_name = name.lower()
        for tbl_name, tbl in self.tables.items():
            if tbl_name.lower() == lower_name:
                return tbl
        return None
