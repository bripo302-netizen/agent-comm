"""
Agent Comm — CE Listener
========================
Lightweight Python process that runs on CE's machine.
Polls Supabase for new commands → types them into Cowork's chat box.

Usage:
    pip install pyautogui requests pygetwindow
    python ce_listener.py

Runs as a background process. Ctrl+C to stop.
"""

import time
import json
import sys
import logging
import requests
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = "https://slvhuervxesffwggdbuo.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNsdmh1ZXJ2eGVzZmZ3Z2dkYnVvIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NjM4MzksImV4cCI6MjA5NDAzOTgzOX0."
    "4mzERzI6A8Ff9Z-mdA0qSriQaAR2A7Kw6FA7xWyX20E"
)
AGENT_ID = "CE"
POLL_INTERVAL = 30          # seconds between checks
COWORK_WINDOW_TITLE = "Claude"  # window title to find (adjust if different)

# ─── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ce-listener")

# ─── Supabase API helpers ─────────────────────────────────────────────
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def fetch_new_commands():
    """Pull unread commands for CE (status = sent)."""
    url = (
        f"{SUPABASE_URL}/rest/v1/messages"
        f"?to_agent=eq.{AGENT_ID}"
        f"&channel=eq.command"
        f"&status=eq.sent"
        f"&order=created_at.asc"
        f"&select=id,from_agent,content,created_at"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Supabase fetch failed: {e}")
        return []

def mark_delivered(msg_id):
    """Mark a message as delivered so we don't re-process it."""
    url = f"{SUPABASE_URL}/rest/v1/messages?id=eq.{msg_id}"
    try:
        resp = requests.patch(
            url,
            headers=HEADERS,
            json={"status": "delivered"},
            timeout=10
        )
        resp.raise_for_status()
    except Exception as e:
        log.error(f"Failed to mark {msg_id[:8]} as delivered: {e}")

# ─── Desktop automation ───────────────────────────────────────────────
def type_into_cowork(text):
    """Find the Cowork/Claude window and type a message into the chat box."""
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        log.error(
            "Missing dependencies. Run:\n"
            "  pip install pyautogui pygetwindow"
        )
        return False

    # Find the Claude/Cowork window
    windows = gw.getWindowsWithTitle(COWORK_WINDOW_TITLE)
    if not windows:
        log.warning(f"No window found with title containing '{COWORK_WINDOW_TITLE}'")
        # Try alternate titles
        for alt in ["Cowork", "Claude Desktop", "Claude.ai"]:
            windows = gw.getWindowsWithTitle(alt)
            if windows:
                break

    if not windows:
        log.error("Could not find Cowork/Claude window. Is the app open?")
        return False

    win = windows[0]

    # Bring window to front
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.5)  # let window come to foreground
    except Exception as e:
        log.warning(f"Could not activate window: {e}")
        # On some Windows versions, activate() can fail but the window
        # may still be in foreground. Continue anyway.

    # The chat input is typically at the bottom of the window.
    # Click near the center-bottom to focus the input field.
    # We use the window's position + offset.
    input_x = win.left + (win.width // 2)
    input_y = win.top + win.height - 80  # ~80px from bottom edge

    pyautogui.click(input_x, input_y)
    time.sleep(0.3)

    # Type short nudge only — CE uses check_inbox MCP tool for full content
    pyautogui.write(text, interval=0.02)
    time.sleep(0.5)
    pyautogui.press("enter")

    return True

# ─── Format the message for Cowork chat ───────────────────────────────
def format_for_chat(msg):
    """Short nudge only — CE uses check_inbox MCP tool for full content."""
    from_agent = msg["from_agent"]
    msg_id = msg["id"][:8]
    content_preview = msg["content"][:80].replace("\n", " ")
    return f"New message from {from_agent} ({msg_id}): {content_preview}... Run check_inbox for full content."

# ─── Main loop ────────────────────────────────────────────────────────
def main():
    log.info(f"CE Listener started — polling every {POLL_INTERVAL}s")
    log.info(f"Watching for commands to agent: {AGENT_ID}")
    log.info(f"Looking for window: '{COWORK_WINDOW_TITLE}'")
    log.info("Press Ctrl+C to stop.\n")

    consecutive_errors = 0

    while True:
        try:
            messages = fetch_new_commands()
            consecutive_errors = 0  # reset on success

            if messages:
                log.info(f"Found {len(messages)} new command(s)!")

                for msg in messages:
                    msg_id = msg["id"]
                    short_id = msg_id[:8]

                    log.info(f"  [{short_id}] from {msg['from_agent']}: {msg['content'][:80]}...")

                    # Mark delivered FIRST so we don't re-process on next poll
                    mark_delivered(msg_id)

                    # Type into Cowork
                    chat_text = format_for_chat(msg)
                    success = type_into_cowork(chat_text)

                    if success:
                        log.info(f"  [{short_id}] ✓ Typed into Cowork")
                    else:
                        log.warning(f"  [{short_id}] ✗ Could not type into Cowork (window not found?)")
                        log.warning(f"  Message content: {msg['content']}")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("\nShutting down CE Listener.")
            sys.exit(0)

        except Exception as e:
            consecutive_errors += 1
            log.error(f"Unexpected error: {e}")

            if consecutive_errors >= 5:
                backoff = min(300, POLL_INTERVAL * consecutive_errors)
                log.warning(f"  {consecutive_errors} consecutive errors — backing off to {backoff}s")
                time.sleep(backoff)
            else:
                time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
