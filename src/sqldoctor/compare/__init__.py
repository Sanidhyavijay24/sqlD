"""
@file __init__.py
@description Result comparison module for SQL Doctor
@module sqldoctor/compare
"""

from sqldoctor.compare.comparator import ResultComparator
from sqldoctor.compare.result import ComparisonDetails, ComparisonVerdict

__all__ = ["ResultComparator", "ComparisonDetails", "ComparisonVerdict"]
