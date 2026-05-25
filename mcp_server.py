"""
Agent Comm — MCP Server
========================
Exposes Supabase-backed messaging as native Claude tools.
Same server runs on both CL and CE machines — configured by AGENT_ID env var.

Setup:
    pip install mcp httpx

Register in Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "agent-comm": {
          "command": "python",
          "args": ["C:/path/to/mcp_server.py"],
          "env": { "AGENT_ID": "CL" }
        }
      }
    }

Tools exposed:
    - send_message    → dispatch a command to another agent
    - check_inbox     → pull new messages for this agent
    - mark_status     → update message status (delivered/read/executed)
    - post_response   → post a response back from this agent
    - get_audit_trail → fetch recent message history (all agents)
    - bulk_archive    → mark all messages before a date as executed (cleanup)
"""

import os
import json
import asyncio
from datetime import datetime, timezone

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ─── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get(
    "AGENTCOMM_URL",
    "https://slvhuervxesffwggdbuo.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "AGENTCOMM_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNsdmh1ZXJ2eGVzZmZ3Z2dkYnVvIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NjM4MzksImV4cCI6MjA5NDAzOTgzOX0."
    "4mzERzI6A8Ff9Z-mdA0qSriQaAR2A7Kw6FA7xWyX20E"
)
AGENT_ID = os.environ.get("AGENT_ID", "CL")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# ─── Supabase helpers ─────────────────────────────────────────────────
async def supabase_get(path: str, params: dict = None) -> list:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=HEADERS,
            params=params or {},
        )
        resp.raise_for_status()
        return resp.json()


async def supabase_post(path: str, data: dict) -> dict:
    headers = {**HEADERS, "Prefer": "return=representation"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=headers,
            json=data,
        )
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) and result else result


async def supabase_patch(path: str, data: dict) -> None:
    headers = {**HEADERS, "Prefer": "return=minimal"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=headers,
            json=data,
        )
        resp.raise_for_status()


async def supabase_patch_count(path: str, data: dict) -> int:
    """PATCH with count header — returns number of rows affected."""
    headers = {**HEADERS, "Prefer": "return=representation,count=exact"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=headers,
            json=data,
        )
        resp.raise_for_status()
        result = resp.json()
        return len(result) if isinstance(result, list) else 0


# ─── MCP Server ───────────────────────────────────────────────────────
app = Server("agent-comm")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_message",
            description=(
                "Send a command/message to another agent via Agent Comm. "
                "The message will appear in the target agent's inbox within 30 seconds. "
                f"You are agent '{AGENT_ID}'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "to_agent": {
                        "type": "string",
                        "description": "Target agent ID (e.g. 'CE', 'CL')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content — task description, question, or instruction",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["normal", "high", "urgent"],
                        "description": "Message priority (default: normal). 'urgent' = needs_approval flag for human confirmation.",
                        "default": "normal",
                    },
                },
                "required": ["to_agent", "content"],
            },
        ),
        Tool(
            name="check_inbox",
            description=(
                f"Check for new unread messages/commands for agent '{AGENT_ID}'. "
                "Returns messages with status 'sent' (not yet picked up). "
                "After reading, use mark_status to update them."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_delivered": {
                        "type": "boolean",
                        "description": "Also include 'delivered' messages (default: false, only 'sent')",
                        "default": False,
                    },
                    "since": {
                        "type": "string",
                        "description": "Only return messages after this ISO date (e.g. '2026-05-25'). Default: no filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default: 50). Set 0 for unlimited.",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="post_response",
            description=(
                f"Post a response/update from agent '{AGENT_ID}' back to the orchestrator. "
                "Use this for task completion reports, progress updates, or blocker notifications."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Response content — result summary, progress update, or blocker description",
                    },
                    "msg_type": {
                        "type": "string",
                        "enum": ["result", "progress", "blocker", "question"],
                        "description": "Type of response (default: result)",
                        "default": "result",
                    },
                    "ref_msg_id": {
                        "type": "string",
                        "description": "Optional: ID of the original command this responds to",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="mark_status",
            description=(
                "Update the status of a message. "
                "Lifecycle: sent → delivered → read → executed"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "msg_id": {
                        "type": "string",
                        "description": "Message UUID to update",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["delivered", "read", "executed"],
                        "description": "New status",
                    },
                },
                "required": ["msg_id", "status"],
            },
        ),
        Tool(
            name="get_audit_trail",
            description=(
                "Fetch recent message history across all agents. "
                "Shows the full communication timeline for visibility."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of messages to return (default: 20, max: 100)",
                        "default": 20,
                    },
                    "agent_filter": {
                        "type": "string",
                        "description": "Filter to messages involving this agent (sent by or sent to)",
                    },
                },
            },
        ),
        Tool(
            name="bulk_archive",
            description=(
                "Mark all messages before a given date as 'executed'. "
                "Use this to clean up old inbox messages after archiving them to disk. "
                "Returns the count of messages updated."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "before_date": {
                        "type": "string",
                        "description": "ISO date (e.g. '2026-05-25'). All messages with created_at before this date will be marked 'executed'.",
                    },
                    "include_today": {
                        "type": "boolean",
                        "description": "If true, also archives messages FROM before_date (uses <=). Default: false (uses <).",
                        "default": False,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, only count messages that WOULD be archived without changing them. Default: false.",
                        "default": False,
                    },
                },
                "required": ["before_date"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "send_message":
            return await handle_send_message(arguments)
        elif name == "check_inbox":
            return await handle_check_inbox(arguments)
        elif name == "post_response":
            return await handle_post_response(arguments)
        elif name == "mark_status":
            return await handle_mark_status(arguments)
        elif name == "get_audit_trail":
            return await handle_get_audit_trail(arguments)
        elif name == "bulk_archive":
            return await handle_bulk_archive(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except httpx.HTTPStatusError as e:
        return [TextContent(
            type="text",
            text=f"Supabase API error: {e.response.status_code} — {e.response.text}"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


# ─── Tool handlers ────────────────────────────────────────────────────

async def handle_send_message(args: dict) -> list[TextContent]:
    to_agent = args["to_agent"].upper()
    content = args["content"]
    priority = args.get("priority", "normal")

    data = {
        "from_agent": AGENT_ID,
        "to_agent": to_agent,
        "content": content,
        "channel": "command",
        "status": "sent",
    }

    result = await supabase_post("messages", data)
    msg_id = result.get("id", "unknown")

    return [TextContent(
        type="text",
        text=(
            f"Message dispatched to {to_agent}.\n"
            f"  ID: {msg_id}\n"
            f"  Priority: {priority}\n"
            f"  Content: {content[:120]}{'...' if len(content) > 120 else ''}\n"
            f"  Status: sent → {to_agent} listener will pick up within 30s"
        ),
    )]


async def handle_check_inbox(args: dict) -> list[TextContent]:
    include_delivered = args.get("include_delivered", False)
    since = args.get("since")
    limit = args.get("limit", 50)

    if include_delivered:
        status_filter = "status=in.(sent,delivered)"
    else:
        status_filter = "status=eq.sent"

    date_filter = f"&created_at=gte.{since}T00:00:00Z" if since else ""
    limit_clause = f"&limit={limit}" if limit > 0 else ""

    # Check commands sent TO this agent
    commands = await supabase_get(
        f"messages?to_agent=eq.{AGENT_ID}&channel=eq.command&{status_filter}"
        f"{date_filter}{limit_clause}&order=created_at.asc&select=*"
    )

    # Check inbox responses directed at this agent (from other agents)
    responses = await supabase_get(
        f"messages?to_agent=eq.{AGENT_ID}&channel=eq.inbox&{status_filter}"
        f"{date_filter}{limit_clause}&order=created_at.asc&select=*"
    )

    # Also check general inbox posts from other agents (no specific to_agent)
    general = await supabase_get(
        f"messages?channel=eq.inbox&{status_filter}"
        f"&from_agent=neq.{AGENT_ID}"
        f"&to_agent=is.null"
        f"{date_filter}{limit_clause}&order=created_at.asc&select=*"
    )

    all_msgs = commands + responses + general

    if not all_msgs:
        return [TextContent(type="text", text=f"No new messages for {AGENT_ID}.")]

    lines = [f"📬 {len(all_msgs)} message(s) for {AGENT_ID}:\n"]
    for m in all_msgs:
        lines.append(
            f"  [{m['id']}] {m['from_agent']} → {AGENT_ID} | "
            f"{m['status']} | {m['channel']}\n"
            f"    {m['content']}\n"
            f"    Time: {m['created_at']}\n"
        )

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_post_response(args: dict) -> list[TextContent]:
    content = args["content"]
    msg_type = args.get("msg_type", "result")
    ref_msg_id = args.get("ref_msg_id")

    data = {
        "from_agent": AGENT_ID,
        "content": content,
        "channel": "inbox",
        "status": "sent",
    }

    result = await supabase_post("messages", data)
    msg_id = result.get("id", "unknown")

    # If this is responding to a specific command, mark it as executed
    if ref_msg_id and msg_type == "result":
        try:
            await supabase_patch(
                f"messages?id=eq.{ref_msg_id}",
                {"status": "executed"},
            )
        except Exception:
            pass  # non-critical

    return [TextContent(
        type="text",
        text=(
            f"Response posted from {AGENT_ID}.\n"
            f"  ID: {msg_id}\n"
            f"  Type: {msg_type}\n"
            f"  Content: {content[:120]}{'...' if len(content) > 120 else ''}"
        ),
    )]


async def handle_mark_status(args: dict) -> list[TextContent]:
    msg_id = args["msg_id"]
    status = args["status"]

    await supabase_patch(
        f"messages?id=eq.{msg_id}",
        {"status": status},
    )

    return [TextContent(
        type="text",
        text=f"Message {msg_id[:8]}... status updated to '{status}'.",
    )]


async def handle_get_audit_trail(args: dict) -> list[TextContent]:
    limit = min(args.get("limit", 20), 100)
    agent_filter = args.get("agent_filter")

    if agent_filter:
        agent = agent_filter.upper()
        msgs = await supabase_get(
            f"messages?or=(from_agent.eq.{agent},to_agent.eq.{agent})"
            f"&order=created_at.desc&limit={limit}&select=*"
        )
    else:
        msgs = await supabase_get(
            f"messages?order=created_at.desc&limit={limit}&select=*"
        )

    if not msgs:
        return [TextContent(type="text", text="No messages in audit trail.")]

    lines = [f"📋 Audit Trail (last {len(msgs)} messages):\n"]
    for m in reversed(msgs):  # chronological order
        direction = "→" if m.get("to_agent") else "↩"
        to_part = f" {direction} {m['to_agent']}" if m.get("to_agent") else ""
        ts = m["created_at"][:19].replace("T", " ")

        lines.append(
            f"  {ts} | {m['from_agent']}{to_part} | "
            f"{m['status']} | {m['channel']}\n"
            f"    {m['content']}\n"
        )

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_bulk_archive(args: dict) -> list[TextContent]:
    before_date = args["before_date"]
    include_today = args.get("include_today", False)
    dry_run = args.get("dry_run", False)

    # Validate date format
    try:
        datetime.strptime(before_date, "%Y-%m-%d")
    except ValueError:
        return [TextContent(
            type="text",
            text=f"Invalid date format: '{before_date}'. Use YYYY-MM-DD.",
        )]

    op = "lte" if include_today else "lt"
    date_ts = f"{before_date}T00:00:00Z"
    filter_path = (
        f"messages?created_at={op}.{date_ts}"
        f"&status=in.(sent,delivered,read)"
    )

    if dry_run:
        # Count only
        msgs = await supabase_get(f"{filter_path}&select=id,status,created_at")
        status_counts = {}
        for m in msgs:
            s = m["status"]
            status_counts[s] = status_counts.get(s, 0) + 1
        breakdown = ", ".join(f"{s}: {c}" for s, c in sorted(status_counts.items()))
        return [TextContent(
            type="text",
            text=(
                f"DRY RUN — {len(msgs)} message(s) would be archived.\n"
                f"  Filter: created_at {op} {date_ts}, status in (sent, delivered, read)\n"
                f"  Breakdown: {breakdown or 'none'}"
            ),
        )]

    # Execute the bulk update
    count = await supabase_patch_count(
        filter_path,
        {"status": "executed"},
    )

    return [TextContent(
        type="text",
        text=(
            f"✅ Archived {count} message(s).\n"
            f"  Filter: created_at {op} {date_ts}\n"
            f"  All matching sent/delivered/read → executed.\n"
            f"  check_inbox will no longer return these messages."
        ),
    )]


# ─── Entry point ──────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
