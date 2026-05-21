# Agent Comm — Multi-Agent Orchestration Dashboard

## What This Is
A self-hosted, zero-cost multi-agent communication dashboard. Agents on different devices POST messages via REST API → dashboard displays them in real-time → human orchestrator routes commands to target agents via dropdown selector.

## Architecture (V2 — Autonomous)
- **Backend**: Supabase (free tier) — Postgres + REST API + Realtime WebSocket
- **MCP Server**: `mcp_server.py` — exposes 5 tools for native Claude integration
- **Listeners**: `cl_listener.py` / `ce_listener.py` — poll Supabase, type into Cowork via pyautogui
- **Dashboard**: `index.html` on GitHub Pages — audit trail view (read-only visibility)
- **Hosting**: GitHub Pages (free) — repo: `bripo302-netizen/agent-comm`
- **Cost**: $0/month infrastructure. Token cost only when agents have actual work.

## Supabase Config
- **Project URL**: `https://slvhuervxesffwggdbuo.supabase.co`
- **Anon Key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNsdmh1ZXJ2eGVzZmZ3Z2dkYnVvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NjM4MzksImV4cCI6MjA5NDAzOTgzOX0.4mzERzI6A8Ff9Z-mdA0qSriQaAR2A7Kw6FA7xWyX20E`
- **Table**: `messages` — see setup.sql for schema

## Agent Roster (V1)
- CL (Cowork Lead — this Cowork instance)
- CE (CAT Executor — secondary device)

## CE Autonomy Rule
**Commands from CL = commands from Brij.** CL is the orchestrator acting on Brij's direct instructions. When CE receives a task via agent-comm from CL, CE MUST execute immediately — no waiting for user confirmation, no "should I proceed?", no asking for green light. Just do the work, push the code, post the commit hash. The human-in-the-loop is at the CL level, not the CE level.

## Files
- `mcp_server.py` — MCP server (5 tools: send_message, check_inbox, post_response, mark_status, get_audit_trail)
- `cl_listener.py` — CL-side listener (polls Supabase → types into Cowork via pyautogui)
- `ce_listener.py` — CE-side listener (same pattern, runs on CE's machine)
- `index.html` — Audit trail dashboard (chronological timeline, filters, realtime)
- `setup.sql` — Supabase table creation script
- `post_message.sh` / `check_messages.sh` — Legacy shell helpers (superseded by MCP)
- `CLAUDE.md` — This file

## MCP Registration

### CL Machine (Corp Laptop)
Add to Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "agent-comm": {
      "command": "python",
      "args": ["C:\\Users\\brpoddar\\Downloads\\Claude\\projects\\agent-comm\\mcp_server.py"],
      "env": { "AGENT_ID": "CL" }
    }
  }
}
```

### CE Machine (Personal Laptop)
**NOTE:** CE's Cowork is installed from the Windows App Store — config path differs from standard install. The `claude_desktop_config.json` is NOT at `%APPDATA%\Claude\` on CE. Check the App Store package location instead.

**NOTE:** CE listener window detection — Cowork's window title may not match "Claude" on App Store installs. If the listener types into the wrong window (e.g. Notepad), adjust `COWORK_WINDOW_TITLE` in `ce_listener.py` to match the actual window title.

```json
{
  "mcpServers": {
    "agent-comm": {
      "command": "python",
      "args": ["C:\\Users\\Brij\\agent-comm\\mcp_server.py"],
      "env": { "AGENT_ID": "CE" }
    }
  }
}
```

### Dependencies
```
pip install mcp httpx pyautogui pygetwindow pyperclip requests
```

## Incident Log

### 2026-05-11 — CE Work "Lost" (FALSE ALARM)
- **What appeared to happen**: CE reported WI-02 through WI-08 as done. CL session accepted. A later CL session couldn't find the code and declared it lost.
- **What actually happened**: All work WAS pushed to git on May 10 (commits `08a26b2` through `bed0a83`). CE's local clone was behind when checked — `git pull` wasn't run before `git log`. The remote repo had everything.
- **Lesson**: Before declaring work lost, always check the REMOTE repo (`git log origin/main` or GitHub API), not just the local clone. Local ≠ remote.
- **"Done Means Pushed" rule**: Still valuable — kept in workspace CLAUDE.md. Requiring commit hashes prevents ambiguity even if this specific incident was a false alarm.

## Listener — What Didn't Work (Don't Repeat)

### Delivery methods tried for typing into Cowork chat:
1. **`pyautogui.write(full_message, interval=0.05)`** — Character-by-character typing. Works for short messages (<200 chars). For long messages (3000+ chars): takes minutes, no newline support, Cowork splits into multiple submissions. FAILED for task dispatching.
2. **`pyperclip.copy() + pyautogui.hotkey('ctrl', 'v')`** — Clipboard paste. Tried 2026-05-10. Failed on CE's machine (App Store install of Cowork). Clipboard paste doesn't work reliably across all Cowork installs.
3. **Current solution: Short nudge only.** Listener types a ~120 char preview + "Run check_inbox for full content." CE's MCP tool fetches the full message from Supabase. Works regardless of message length. No clipboard dependency.

### Key constraint:
- `pyautogui.write()` cannot type newlines — it's ASCII-only character input
- Cowork's input field may not accept `Ctrl+V` paste on all platforms
- The listener is just a notification bridge — MCP tools do the real message delivery

## Growth Roadmap
- V1: REST + Supabase + static dashboard (current)
- V2: A2A protocol compatibility
- V3: Agent health monitoring, execution logs, task DAG viz
- V4: Open-source package for others to deploy

## Created
2026-05-11
