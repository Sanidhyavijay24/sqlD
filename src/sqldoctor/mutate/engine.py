"""
@file engine.py
@description AST mutation engine generating deterministic query mutants via sqlglot
@module sqldoctor/mutate/engine
"""

from collections.abc import Callable
from typing import Any

from sqlglot import Expression, exp

from sqldoctor.mutate.models import Mutant, MutationScore
from sqldoctor.sql.ast import parse_sql


class ASTMutator:
    """Generates deterministic AST mutations of a PostgreSQL query."""

    def generate_mutants(self, sql_query: str) -> list[Mutant]:
        """Generate all applicable deterministic AST mutants for the query.

        Args:
            sql_query: Input PostgreSQL SQL query.

        Returns:
            List of generated Mutant instances.
        """
        ast = parse_sql(sql_query)
        mutants: list[Mutant] = []
        mutant_idx = 0

        # Rule 1: Flip comparison operators
        for node in ast.walk():
            replacement: Expression | None = None
            rule_desc = ""

            if isinstance(node, exp.GT):
                replacement = exp.GTE(this=node.this.copy(), expression=node.expression.copy())
                rule_desc = "Flipped > to >="
            elif isinstance(node, exp.GTE):
                replacement = exp.GT(this=node.this.copy(), expression=node.expression.copy())
                rule_desc = "Flipped >= to >"
            elif isinstance(node, exp.LT):
                replacement = exp.LTE(this=node.this.copy(), expression=node.expression.copy())
                rule_desc = "Flipped < to <="
            elif isinstance(node, exp.LTE):
                replacement = exp.LT(this=node.this.copy(), expression=node.expression.copy())
                rule_desc = "Flipped <= to <"
            elif isinstance(node, exp.EQ):
                replacement = exp.NEQ(this=node.this.copy(), expression=node.expression.copy())
                rule_desc = "Flipped = to <>"
            elif isinstance(node, exp.NEQ):
                replacement = exp.EQ(this=node.this.copy(), expression=node.expression.copy())
                rule_desc = "Flipped <> to ="

            if replacement is not None:
                mutant_ast = ast.copy()
                # Find matching node in clone and replace
                for target in mutant_ast.walk():
                    if type(target) is type(node) and target.sql() == node.sql():
                        target.replace(replacement)
                        mutant_sql = mutant_ast.sql(dialect="postgres")
                        if mutant_sql != ast.sql(dialect="postgres"):
                            mutant_idx += 1
                            mutants.append(
                                Mutant(
                                    id=f"mutant_{mutant_idx}",
                                    rule_name="FlipComparison",
                                    description=rule_desc,
                                    original_sql=sql_query,
                                    mutated_sql=mutant_sql,
                                )
                            )
                        break

        # Rule 2: Shift integer constants (+1 and -1)
        for node in ast.walk():
            if isinstance(node, exp.Literal) and node.is_int:
                try:
                    val = int(node.this)
                    for delta, name in [
                        (-1, "decremented by 1"),
                        (1, "incremented by 1"),
                    ]:
                        mutant_ast = ast.copy()
                        for target in mutant_ast.walk():
                            if (
                                isinstance(target, exp.Literal)
                                and target.is_int
                                and target.this == node.this
                            ):
                                target.replace(exp.Literal.number(val + delta))
                                mutant_sql = mutant_ast.sql(dialect="postgres")
                                if mutant_sql != ast.sql(dialect="postgres"):
                                    mutant_idx += 1
                                    mutants.append(
                                        Mutant(
                                            id=f"mutant_{mutant_idx}",
                                            rule_name="ShiftConstant",
                                            description=f"Constant {val} {name}",
                                            original_sql=sql_query,
                                            mutated_sql=mutant_sql,
                                        )
                                    )
                                break
                except (ValueError, TypeError):
                    pass

        # Rule 3: Swap AND and OR
        for node in ast.walk():
            if isinstance(node, exp.And):
                mutant_ast = ast.copy()
                for target in mutant_ast.walk():
                    if isinstance(target, exp.And) and target.sql() == node.sql():
                        target.replace(
                            exp.Or(
                                this=target.this.copy(),
                                expression=target.expression.copy(),
                            )
                        )
                        mutant_idx += 1
                        mutants.append(
                            Mutant(
                                id=f"mutant_{mutant_idx}",
                                rule_name="SwapBoolean",
                                description="Swapped AND to OR",
                                original_sql=sql_query,
                                mutated_sql=mutant_ast.sql(dialect="postgres"),
                            )
                        )
                        break
            elif isinstance(node, exp.Or):
                mutant_ast = ast.copy()
                for target in mutant_ast.walk():
                    if isinstance(target, exp.Or) and target.sql() == node.sql():
                        target.replace(
                            exp.And(
                                this=target.this.copy(),
                                expression=target.expression.copy(),
                            )
                        )
                        mutant_idx += 1
                        mutants.append(
                            Mutant(
                                id=f"mutant_{mutant_idx}",
                                rule_name="SwapBoolean",
                                description="Swapped OR to AND",
                                original_sql=sql_query,
                                mutated_sql=mutant_ast.sql(dialect="postgres"),
                            )
                        )
                        break

        # Rule 4: Toggle DISTINCT
        select_node = ast.find(exp.Select)
        if select_node:
            distinct_arg = select_node.args.get("distinct")
            mutant_ast = ast.copy()
            target_select = mutant_ast.find(exp.Select)
            if target_select:
                if distinct_arg is not None:
                    target_select.set("distinct", None)
                    mutant_idx += 1
                    mutants.append(
                        Mutant(
                            id=f"mutant_{mutant_idx}",
                            rule_name="ToggleDistinct",
                            description="Removed DISTINCT from SELECT",
                            original_sql=sql_query,
                            mutated_sql=mutant_ast.sql(dialect="postgres"),
                        )
                    )
                else:
                    target_select.set("distinct", exp.Distinct())
                    mutant_idx += 1
                    mutants.append(
                        Mutant(
                            id=f"mutant_{mutant_idx}",
                            rule_name="ToggleDistinct",
                            description="Added DISTINCT to SELECT",
                            original_sql=sql_query,
                            mutated_sql=mutant_ast.sql(dialect="postgres"),
                        )
                    )

        # Rule 5: Swap Aggregate Functions (COUNT <-> SUM, MIN <-> MAX)
        for node in ast.walk():
            if isinstance(node, (exp.Count, exp.Sum, exp.Min, exp.Max, exp.Avg)):
                mutant_ast = ast.copy()
                for target in mutant_ast.walk():
                    if type(target) is type(node) and target.sql() == node.sql():
                        replacement_fn: Expression
                        desc = ""
                        if isinstance(target, exp.Count):
                            replacement_fn = exp.Sum(
                                this=target.this.copy() if target.this else exp.Literal.number(1)
                            )
                            desc = "Changed COUNT to SUM"
                        elif isinstance(target, exp.Sum):
                            replacement_fn = exp.Avg(this=target.this.copy())
                            desc = "Changed SUM to AVG"
                        elif isinstance(target, exp.Min):
                            replacement_fn = exp.Max(this=target.this.copy())
                            desc = "Changed MIN to MAX"
                        else:
                            replacement_fn = exp.Min(this=target.this.copy())
                            desc = "Changed aggregate function"

                        target.replace(replacement_fn)
                        mutant_idx += 1
                        mutants.append(
                            Mutant(
                                id=f"mutant_{mutant_idx}",
                                rule_name="SwapAggregate",
                                description=desc,
                                original_sql=sql_query,
                                mutated_sql=mutant_ast.sql(dialect="postgres"),
                            )
                        )
                        break

        # Rule 6: Drop WHERE predicates
        where_node = ast.find(exp.Where)
        if where_node:
            mutant_ast = ast.copy()
            target_where = mutant_ast.find(exp.Where)
            if target_where:
                target_where.replace(exp.true())
                mutant_idx += 1
                mutants.append(
                    Mutant(
                        id=f"mutant_{mutant_idx}",
                        rule_name="DropPredicate",
                        description="Removed WHERE clause condition (set to TRUE)",
                        original_sql=sql_query,
                        mutated_sql=mutant_ast.sql(dialect="postgres"),
                    )
                )

        return mutants

    def evaluate_adequacy(
        self,
        mutants: list[Mutant],
        execute_fn: Callable[[str], list[tuple[Any, ...]]],
        original_output: list[tuple[Any, ...]],
    ) -> MutationScore:
        """Evaluate how many mutants are killed by output disparity against original query output.

        Args:
            mutants: List of mutants to evaluate.
            execute_fn: Callable taking SQL query and returning rows.
            original_output: Output rows of original query on the dataset pool.

        Returns:
            MutationScore with kill ratios and survived descriptions.
        """
        if not mutants:
            return MutationScore(
                total_mutants=0,
                killed_mutants=0,
                survived_mutants=0,
                score=1.0,
                survived_descriptions=[],
            )

        killed = 0
        survived_descriptions: list[str] = []

        for m in mutants:
            try:
                mutant_output = execute_fn(m.mutated_sql)
                if mutant_output != original_output:
                    m.is_killed = True
                    killed += 1
                else:
                    survived_descriptions.append(f"{m.rule_name}: {m.description}")
            except Exception:
                # Query syntax/execution error caused by mutation counts as killed
                m.is_killed = True
                killed += 1

        total = len(mutants)
        score = killed / total if total > 0 else 1.0

        return MutationScore(
            total_mutants=total,
            killed_mutants=killed,
            survived_mutants=total - killed,
            score=round(score, 4),
            survived_descriptions=survived_descriptions,
        )
