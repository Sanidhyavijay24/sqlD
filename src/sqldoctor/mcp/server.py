"""
@file server.py
@description FastMCP server exposing verify_rewrite, diagnose_query, and replay_receipt tools
@module sqldoctor/mcp/server
"""

from typing import Any

from sqldoctor.mcp.tools import (
    diagnose_query_tool,
    replay_receipt_tool,
    verify_rewrite_tool,
)


def create_mcp_server() -> Any:
    """Create and configure the SQL Doctor FastMCP server instance."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "The 'mcp' package is required to run the MCP server. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    mcp = FastMCP("sqld")
    mcp.add_tool(
        verify_rewrite_tool,
        name="verify_rewrite",
        description="Deterministically verify if candidate_sql is semantically equivalent to original_sql.",
    )
    mcp.add_tool(
        diagnose_query_tool,
        name="diagnose_query",
        description="Optimize a slow PostgreSQL query with an LLM agent and verify equivalence deterministically.",
    )
    mcp.add_tool(
        replay_receipt_tool,
        name="replay_receipt",
        description="Replay a standalone receipt.sql file and confirm recorded verdict reproduction.",
    )
    return mcp


def run_mcp_server(transport: str = "stdio") -> None:
    """Start the SQL Doctor MCP server on the requested transport."""
    server = create_mcp_server()
    server.run(transport=transport)
