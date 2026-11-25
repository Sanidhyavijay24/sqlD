"""
@file loop.py
@description Diagnostic agent loop: coordinates LLM proposal generation and deterministic adversary verification
@module sqldoctor/agent/loop
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sqldoctor.agent.llm import LLMClient, LLMMessage, LLMToolCall
from sqldoctor.agent.plan import explain_query, is_plan_equivalent
from sqldoctor.config import AppConfig
from sqldoctor.sandbox.client import SandboxClient
from sqldoctor.schema.models import SchemaModel
from sqldoctor.verifier.adversary_verifier import AdversaryVerdictReport, AdversaryVerifier

logger = logging.getLogger(__name__)


class VerifiedCandidate(BaseModel):
    """Record of a verified candidate rewrite."""

    model_config = ConfigDict(extra="forbid")

    candidate_sql: str
    verdict: str
    mutation_score: float
    is_no_op: bool = False
    explanation: str = ""
    report: dict[str, Any] = Field(default_factory=dict)


class RejectedCandidate(BaseModel):
    """Record of a rejected candidate rewrite with counterexample."""

    model_config = ConfigDict(extra="forbid")

    candidate_sql: str
    verdict: str
    disparity_reason: str = ""
    counterexample: dict[str, Any] | None = None
    explanation: str = ""


class IndexProposal(BaseModel):
    """Record of a proposed hypothetical or physical index."""

    model_config = ConfigDict(extra="forbid")

    index_sql: str
    explanation: str = ""


class DiagnosticResult(BaseModel):
    """Comprehensive output of an agent diagnosis run."""

    model_config = ConfigDict(extra="forbid")

    original_sql: str
    verdict: str = Field(
        description="Final verdict: tested_equivalent, conditionally_equivalent, no_op, rejected, unverified"
    )
    best_candidate: str | None = None
    proposals_count: int = 0
    total_cost_usd: float = 0.0
    verified_candidates: list[VerifiedCandidate] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    proposed_indexes: list[IndexProposal] = Field(default_factory=list)
    final_explanation: str = ""
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)


class DiagnosticAgent:
    """Agent loop that prompts LLM for rewrite/index proposals and enforces deterministic verification."""

    AGENT_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "get_schema",
                "description": "Retrieve schema metadata including tables, columns, constraints, and data types without exposing row values.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_stats_summary",
                "description": "Retrieve table row count approximations and column constraints.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "explain",
                "description": "Retrieve normalized PostgreSQL EXPLAIN plan for a query to inspect access paths and join strategies.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL query to explain",
                        }
                    },
                    "required": ["sql"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_candidate",
                "description": "Submit a candidate query rewrite to the deterministic adversary judge. If rejected, returns the exact minimal counterexample dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_sql": {
                            "type": "string",
                            "description": "The candidate rewritten SQL query",
                        }
                    },
                    "required": ["candidate_sql"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "propose_index",
                "description": "Propose a CREATE INDEX statement to accelerate the query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index_sql": {
                            "type": "string",
                            "description": "PostgreSQL CREATE INDEX statement",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Rationale for why this index assists query execution",
                        },
                    },
                    "required": ["index_sql"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit",
                "description": "Conclude diagnosis with the optimal rewrite candidate and detailed performance explanation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_sql": {
                            "type": "string",
                            "description": "The verified optimal SQL query",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Detailed explanation of optimizations achieved",
                        },
                    },
                    "required": ["candidate_sql", "explanation"],
                },
            },
        },
    ]

    def __init__(
        self,
        config: AppConfig,
        db_client: SandboxClient | None = None,
        schema_model: SchemaModel | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.config = config
        self.db_client = db_client
        self.schema_model = schema_model
        self.llm_client = llm_client or LLMClient(
            api_key=config.agent.api_key,
            base_url=config.agent.base_url,
            model=config.agent.model,
            max_cost_usd=config.agent.max_cost_usd,
        )
        self.verifier = AdversaryVerifier(
            seed=config.adversary.seed,
            enumeration_cap=config.adversary.enumeration_cap,
            fuzz_datasets=config.adversary.fuzz_datasets,
            pg_version=f"{config.sandbox.pg_version}.x",
        )

        prompt_path = Path(__file__).parent / "prompts" / "diagnose_v1.txt"
        if prompt_path.is_file():
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        else:
            self.system_prompt = "You are SQL Doctor, an expert PostgreSQL query optimizer."

    def _execute_tool(
        self,
        tool_call: LLMToolCall,
        original_sql: str,
        verified_candidates: list[VerifiedCandidate],
        rejected_candidates: list[RejectedCandidate],
        proposed_indexes: list[IndexProposal],
    ) -> dict[str, Any]:
        """Dispatch tool calls to internal implementations."""
        name = tool_call.function_name
        args = tool_call.arguments

        if name == "get_schema":
            if self.schema_model:
                tables_info = {}
                for tname, tmodel in self.schema_model.tables.items():
                    tables_info[tname] = {
                        "columns": [
                            f"{c.name} {c.data_type}" + (" NOT NULL" if not c.is_nullable else "")
                            for c in tmodel.columns.values()
                        ],
                        "primary_key": [
                            c.columns for c in tmodel.constraints if c.type.value == "PRIMARY KEY"
                        ],
                        "foreign_keys": [
                            {
                                "cols": c.columns,
                                "ref": f"{c.foreign_table}({','.join(c.foreign_columns or [])})",
                            }
                            for c in tmodel.constraints
                            if c.type.value == "FOREIGN KEY"
                        ],
                    }
                return {"schema": tables_info}
            return {"schema": "No schema loaded."}

        elif name == "get_stats_summary":
            if self.schema_model:
                stats = {t: {"row_count_estimate": 1000} for t in self.schema_model.tables}
                return {"stats": stats}
            return {"stats": "No schema loaded."}

        elif name == "explain":
            sql = args.get("sql", original_sql)
            plan = explain_query(self.db_client, sql)
            return {"plan": plan}

        elif name == "verify_candidate":
            candidate_sql = args.get("candidate_sql", "").strip()
            if not candidate_sql:
                return {"error": "Missing candidate_sql"}

            # Plan comparison for no-op detection
            plan_orig = explain_query(self.db_client, original_sql)
            plan_cand = explain_query(self.db_client, candidate_sql)
            is_no_op = is_plan_equivalent(plan_orig, plan_cand)

            if not self.schema_model:
                return {"error": "No schema loaded to verify candidate against."}

            report: AdversaryVerdictReport = self.verifier.verify(
                schema=self.schema_model,
                original_sql=original_sql,
                candidate_sql=candidate_sql,
            )

            if report.verdict == "rejected":
                ce = report.counterexample.model_dump() if report.counterexample else None
                reason = (
                    report.counterexample.reason if report.counterexample else "Result sets differ"
                )
                rejected_candidates.append(
                    RejectedCandidate(
                        candidate_sql=candidate_sql,
                        verdict="rejected",
                        disparity_reason=reason,
                        counterexample=ce,
                        explanation=args.get("explanation", ""),
                    )
                )
                return {
                    "verdict": "rejected",
                    "counterexample": ce,
                    "disparity_reason": reason,
                    "message": "Candidate rejected: produced divergent results on test dataset. Refine candidate to resolve this difference.",
                }
            else:
                score = float(report.mutants.get("score", 1.0))
                vc = VerifiedCandidate(
                    candidate_sql=candidate_sql,
                    verdict=report.verdict,
                    mutation_score=score,
                    is_no_op=is_no_op,
                    explanation=args.get("explanation", ""),
                    report=report.model_dump(),
                )
                verified_candidates.append(vc)
                return {
                    "verdict": report.verdict,
                    "mutation_score": score,
                    "is_no_op": is_no_op,
                    "message": "Candidate verified equivalent by adversary judge."
                    + (
                        " Warning: execution plan is identical to original (no-op)."
                        if is_no_op
                        else ""
                    ),
                }

        elif name == "propose_index":
            index_sql = args.get("index_sql", "").strip()
            exp = args.get("explanation", "")
            if index_sql:
                proposed_indexes.append(IndexProposal(index_sql=index_sql, explanation=exp))
                return {
                    "status": "recorded",
                    "index_sql": index_sql,
                    "message": "Index proposal recorded.",
                }
            return {"error": "Missing index_sql"}

        elif name == "submit":
            return {
                "status": "submitted",
                "candidate_sql": args.get("candidate_sql"),
                "explanation": args.get("explanation", ""),
            }

        return {"error": f"Unknown tool: {name}"}

    def run(self, original_sql: str, schema_sql: str | None = None) -> DiagnosticResult:
        """Execute diagnostic optimization loop on original query.

        Args:
            original_sql: The PostgreSQL query to optimize.
            schema_sql: Optional DDL SQL to load if schema_model was not injected.

        Returns:
            DiagnosticResult with all verified/rejected candidates and audit trail.
        """
        # Load schema DDL if provided and needed
        if schema_sql and not self.schema_model:
            from sqldoctor.schema.loader import parse_ddl_to_schema

            self.schema_model = parse_ddl_to_schema(schema_sql)

        verified_candidates: list[VerifiedCandidate] = []
        rejected_candidates: list[RejectedCandidate] = []
        proposed_indexes: list[IndexProposal] = []
        audit_trail: list[dict[str, Any]] = []

        schema_summary = ""
        if self.schema_model:
            tables_summary = []
            for tname, tmodel in self.schema_model.tables.items():
                cols = [
                    f"{c.name} {c.data_type}" + (" NOT NULL" if not c.is_nullable else "")
                    for c in tmodel.columns.values()
                ]
                tables_summary.append(f"{tname} ({', '.join(cols)})")
            schema_summary = "\n\nSchema Context:\n" + "\n".join(tables_summary)

        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Please analyze and optimize this PostgreSQL query:\n\n```sql\n{original_sql.strip()}\n```{schema_summary}",
            ),
        ]

        proposals_count = 0
        final_verdict = "unverified"
        best_candidate: str | None = None
        final_explanation = ""

        for turn in range(self.config.agent.max_proposals):
            try:
                tools_to_pass = self.AGENT_TOOLS if self.config.agent.use_tools else None
                response = self.llm_client.generate(messages, tools=tools_to_pass, temperature=0.0)
            except Exception as e:
                logger.error("LLM generation failed on turn %d: %s", turn, e)
                audit_trail.append({"turn": turn, "error": str(e)})
                break

            audit_trail.append(
                {
                    "turn": turn,
                    "response": response.model_dump(),
                }
            )

            # If tool calls were generated
            if response.tool_calls:
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                has_submit = False
                for tc in response.tool_calls:
                    if tc.function_name in ("verify_candidate", "submit"):
                        proposals_count += 1

                    tool_output = self._execute_tool(
                        tc,
                        original_sql,
                        verified_candidates,
                        rejected_candidates,
                        proposed_indexes,
                    )

                    messages.append(
                        LLMMessage(
                            role="tool",
                            name=tc.function_name,
                            tool_call_id=tc.id,
                            content=json.dumps(tool_output, default=str),
                        )
                    )

                    if tc.function_name == "submit":
                        has_submit = True
                        cand = tc.arguments.get("candidate_sql")
                        exp = tc.arguments.get("explanation", "")
                        final_explanation = exp

                        # Make sure submitted candidate is verified
                        matching_verified = [
                            vc
                            for vc in verified_candidates
                            if vc.candidate_sql.strip() == (cand or "").strip()
                        ]
                        if not matching_verified and cand and self.schema_model:
                            # Run verification now
                            report = self.verifier.verify(
                                schema=self.schema_model,
                                original_sql=original_sql,
                                candidate_sql=cand,
                            )
                            if report.verdict in (
                                "tested_equivalent",
                                "conditionally_equivalent",
                            ):
                                score = float(report.mutants.get("score", 1.0))
                                verified_candidates.append(
                                    VerifiedCandidate(
                                        candidate_sql=cand,
                                        verdict=report.verdict,
                                        mutation_score=score,
                                        explanation=exp,
                                        report=report.model_dump(),
                                    )
                                )
                                best_candidate = cand
                                final_verdict = report.verdict
                            else:
                                rejected_candidates.append(
                                    RejectedCandidate(
                                        candidate_sql=cand,
                                        verdict="rejected",
                                        disparity_reason=report.counterexample.reason
                                        if report.counterexample
                                        else "Result difference",
                                        counterexample=report.counterexample.model_dump()
                                        if report.counterexample
                                        else None,
                                        explanation=exp,
                                    )
                                )
                                final_verdict = "rejected"
                        elif matching_verified:
                            best_candidate = cand
                            final_verdict = matching_verified[0].verdict

                if has_submit:
                    break
            else:
                # Text-only response
                messages.append(LLMMessage(role="assistant", content=response.content))
                final_explanation = response.content or ""
                # Check if SQL code blocks were returned
                import re

                blocks = re.findall(
                    r"```sql\s*(.*?)\s*```",
                    response.content or "",
                    re.DOTALL | re.IGNORECASE,
                )
                sql_candidates = []
                for block in blocks:
                    clean_block = block.strip()
                    if clean_block.upper().startswith(
                        "CREATE INDEX"
                    ) or clean_block.upper().startswith("CREATE UNIQUE INDEX"):
                        proposed_indexes.append(
                            IndexProposal(
                                index_sql=clean_block,
                                explanation="Proposed index from diagnosis recommendations",
                            )
                        )
                    elif clean_block.upper().startswith("SELECT") or clean_block.upper().startswith(
                        "WITH"
                    ):
                        sql_candidates.append(clean_block)

                if sql_candidates:
                    candidate_sql = sql_candidates[0]
                    proposals_count += 1

                    if self.schema_model:
                        report = self.verifier.verify(
                            schema=self.schema_model,
                            original_sql=original_sql,
                            candidate_sql=candidate_sql,
                        )
                        if report.verdict in (
                            "tested_equivalent",
                            "conditionally_equivalent",
                        ):
                            plan_orig = explain_query(self.db_client, original_sql)
                            plan_cand = explain_query(self.db_client, candidate_sql)
                            is_no_op = is_plan_equivalent(plan_orig, plan_cand)
                            score = float(report.mutants.get("score", 1.0))
                            verified_candidates.append(
                                VerifiedCandidate(
                                    candidate_sql=candidate_sql,
                                    verdict=report.verdict,
                                    mutation_score=score,
                                    is_no_op=is_no_op,
                                    explanation=response.content or "",
                                    report=report.model_dump(),
                                )
                            )
                            best_candidate = candidate_sql
                            final_verdict = "no_op" if is_no_op else report.verdict
                            break
                        else:
                            ce = (
                                report.counterexample.model_dump()
                                if report.counterexample
                                else None
                            )
                            rejected_candidates.append(
                                RejectedCandidate(
                                    candidate_sql=candidate_sql,
                                    verdict="rejected",
                                    disparity_reason=report.counterexample.reason
                                    if report.counterexample
                                    else "Result sets differ",
                                    counterexample=ce,
                                    explanation="Text block proposal",
                                )
                            )
                            # Feed back counterexample to LLM in next turn
                            messages.append(
                                LLMMessage(
                                    role="user",
                                    content=f"Your candidate rewrite produced different results on an adversarial test dataset:\n\n{json.dumps(ce, indent=2, default=str)}\n\nPlease analyze the counterexample and propose a corrected rewrite.",
                                )
                            )
                    else:
                        break
                else:
                    # Model gave explanation without SQL
                    break

        # Select best candidate if not submitted
        if not best_candidate and verified_candidates:
            # Prefer non-no-op tested_equivalent
            candidates = sorted(
                verified_candidates,
                key=lambda c: (
                    not c.is_no_op,
                    c.verdict == "tested_equivalent",
                    c.mutation_score,
                ),
                reverse=True,
            )
            best_candidate = candidates[0].candidate_sql
            final_verdict = "no_op" if candidates[0].is_no_op else candidates[0].verdict
        elif not best_candidate and rejected_candidates:
            final_verdict = "rejected"

        return DiagnosticResult(
            original_sql=original_sql,
            verdict=final_verdict,
            best_candidate=best_candidate,
            proposals_count=proposals_count,
            total_cost_usd=round(self.llm_client.cumulative_cost_usd, 6),
            verified_candidates=verified_candidates,
            rejected_candidates=rejected_candidates,
            proposed_indexes=proposed_indexes,
            final_explanation=final_explanation,
            audit_trail=audit_trail,
        )
