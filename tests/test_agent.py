"""
@file test_agent.py
@description Unit tests for LLM client caching, plan normalizer, and agent diagnostic loop
@module tests/test_agent
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from sqldoctor.agent.llm import LLMClient, LLMResponse, LLMUsage
from sqldoctor.agent.loop import DiagnosticAgent
from sqldoctor.agent.plan import (
    is_plan_equivalent,
    normalize_explain_text,
)
from sqldoctor.config import AppConfig
from sqldoctor.schema.loader import parse_ddl_to_schema


def test_prompt_hash_determinism(tmp_path: Path) -> None:
    """Verify SHA-256 prompt hash is deterministic regardless of key ordering."""
    client = LLMClient(cache_dir=tmp_path / "cache")
    msgs = [
        {"role": "user", "content": "SELECT 1;"},
        {"role": "system", "content": "You are a SQL optimizer."},
    ]
    hash1 = client.compute_prompt_hash(msgs, model="test-model", temperature=0.0)
    hash2 = client.compute_prompt_hash(msgs, model="test-model", temperature=0.0)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_llm_caching(tmp_path: Path) -> None:
    """Verify that cached responses are loaded from disk with zero network call and cost."""
    cache_dir = tmp_path / "cache"
    client = LLMClient(cache_dir=cache_dir, model="test-model")

    msgs = [{"role": "user", "content": "OPTIMIZE QUERY"}]
    p_hash = client.compute_prompt_hash(msgs, model="test-model", temperature=0.0)
    cache_file = cache_dir / f"{p_hash}.json"

    # Pre-populate cache
    cached_payload = {
        "content": "Optimized SQL",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_usd": 0.0001,
        },
        "cached": False,
        "prompt_hash": p_hash,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cached_payload, f)

    resp = client.generate(msgs, temperature=0.0)
    assert resp.cached is True
    assert resp.content == "Optimized SQL"
    assert client.cumulative_cost_usd == 0.0


def test_cost_cap_enforcement(tmp_path: Path) -> None:
    """Verify runtime error raised when cumulative cost exceeds max_cost_usd."""
    client = LLMClient(cache_dir=tmp_path / "cache", max_cost_usd=0.05)
    client.cumulative_cost_usd = 0.06

    msgs = [{"role": "user", "content": "HELLO"}]
    with pytest.raises(RuntimeError, match="LLM cost cap of \\$0.05 exceeded"):
        client.generate(msgs)


def test_plan_normalizer() -> None:
    """Verify stripping of costs, timings, and buffers from raw PostgreSQL EXPLAIN output."""
    raw_plan = """
    Seq Scan on users  (cost=0.00..35.50 rows=10 width=8) (actual time=0.012..0.045 rows=10 loops=1)
      Filter: (age > 21)
      Buffers: shared hit=4 read=1
    Planning Time: 0.125 ms
    Execution Time: 0.065 ms
    """
    normalized = normalize_explain_text(raw_plan)
    assert "cost=" not in normalized
    assert "actual time=" not in normalized
    assert "Planning Time:" not in normalized
    assert "Execution Time:" not in normalized
    assert "Seq Scan on users" in normalized
    assert "Filter: (age > 21)" in normalized


def test_plan_equivalence() -> None:
    """Verify is_plan_equivalent detects identical plan structures."""
    plan1 = "Seq Scan on orders\n  Filter: (status = 'active')"
    plan2 = "Seq Scan on orders\n  Filter: (status = 'active')"
    plan3 = "Index Scan using idx_status on orders\n  Index Cond: (status = 'active')"

    assert is_plan_equivalent(plan1, plan2) is True
    assert is_plan_equivalent(plan1, plan3) is False


def test_diagnostic_agent_loop_with_mock_llm(tmp_path: Path) -> None:
    """Verify agent loop properly coordinates proposal verification, counterexamples, and submit."""
    schema_ddl = """
    CREATE TABLE users (
        id INT PRIMARY KEY,
        name TEXT NOT NULL,
        is_active BOOLEAN NOT NULL
    );
    """
    schema = parse_ddl_to_schema(schema_ddl)
    config = AppConfig()

    class MockLLMClient(LLMClient):
        def __init__(self) -> None:
            super().__init__(cache_dir=tmp_path / "cache")
            self.turn = 0

        def generate(
            self,
            messages: Sequence[Any],
            tools: list[dict[str, Any]] | None = None,
            temperature: float = 0.0,
        ) -> LLMResponse:
            self.turn += 1
            if self.turn == 1:
                # First turn: call get_schema
                from sqldoctor.agent.llm import LLMToolCall

                return LLMResponse(
                    tool_calls=[
                        LLMToolCall(
                            id="call_1",
                            function_name="get_schema",
                            arguments={},
                        )
                    ],
                    usage=LLMUsage(prompt_tokens=50, completion_tokens=20, cost_usd=0.001),
                )
            elif self.turn == 2:
                # Second turn: verify candidate rewrite
                from sqldoctor.agent.llm import LLMToolCall

                return LLMResponse(
                    tool_calls=[
                        LLMToolCall(
                            id="call_2",
                            function_name="verify_candidate",
                            arguments={
                                "candidate_sql": "SELECT id, name FROM users WHERE is_active = TRUE",
                                "explanation": "Explicit boolean comparison",
                            },
                        )
                    ],
                    usage=LLMUsage(prompt_tokens=100, completion_tokens=40, cost_usd=0.002),
                )
            else:
                # Third turn: propose index and submit
                from sqldoctor.agent.llm import LLMToolCall

                return LLMResponse(
                    tool_calls=[
                        LLMToolCall(
                            id="call_3",
                            function_name="propose_index",
                            arguments={
                                "index_sql": "CREATE INDEX idx_users_active ON users (is_active) WHERE is_active = TRUE",
                                "explanation": "Filtered partial index on active users",
                            },
                        ),
                        LLMToolCall(
                            id="call_4",
                            function_name="submit",
                            arguments={
                                "candidate_sql": "SELECT id, name FROM users WHERE is_active = TRUE",
                                "explanation": "Optimized predicate and partial index proposal",
                            },
                        ),
                    ],
                    usage=LLMUsage(prompt_tokens=150, completion_tokens=60, cost_usd=0.003),
                )

    agent = DiagnosticAgent(config=config, schema_model=schema, llm_client=MockLLMClient())
    res = agent.run("SELECT id, name FROM users WHERE is_active")

    assert res.verdict in ("tested_equivalent", "no_op")
    assert res.best_candidate == "SELECT id, name FROM users WHERE is_active = TRUE"
    assert len(res.verified_candidates) >= 1
    assert len(res.proposed_indexes) == 1
    assert "idx_users_active" in res.proposed_indexes[0].index_sql
