"""
Agent Comm — CL Listener
=========================
Runs on CL's machine (corp laptop). Polls Supabase for responses
from CE and types them into Cowork's chat box via pyautogui.

Mirror of ce_listener.py but watches for inbox messages FROM other agents.

Usage:
    pip install pyautogui requests pygetwindow pyperclip
    python cl_listener.py

Runs as a background process. Ctrl+C to stop.
"""

import time
import json
import sys
import logging
import requests

# ─── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = "https://slvhuervxesffwggdbuo.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNsdmh1ZXJ2eGVzZmZ3Z2dkYnVvIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NjM4MzksImV4cCI6MjA5NDAzOTgzOX0."
    "4mzERzI6A8Ff9Z-mdA0qSriQaAR2A7Kw6FA7xWyX20E"
)
AGENT_ID = "CL"
POLL_INTERVAL = 30
COWORK_WINDOW_TITLE = "Claude"

# ─── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("cl-listener")

# ─── Supabase API ────────────────────────────────────────────────────
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


def fetch_new_responses():
    """Pull unread inbox messages from other agents (status = sent)."""
    url = (
        f"{SUPABASE_URL}/rest/v1/messages"
        f"?channel=eq.inbox"
        f"&status=eq.sent"
        f"&from_agent=neq.{AGENT_ID}"
        f"&order=created_at.asc"
        f"&select=id,from_agent,content,channel,created_at"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Supabase fetch failed: {e}")
        return []


def fetch_commands_for_me():
    """Pull unread commands sent TO this agent."""
    url = (
        f"{SUPABASE_URL}/rest/v1/messages"
        f"?to_agent=eq.{AGENT_ID}"
        f"&channel=eq.command"
        f"&status=eq.sent"
        f"&order=created_at.asc"
        f"&select=id,from_agent,content,channel,created_at"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Supabase fetch failed: {e}")
        return []


def mark_delivered(msg_id):
    url = f"{SUPABASE_URL}/rest/v1/messages?id=eq.{msg_id}"
    try:
        resp = requests.patch(url, headers=HEADERS, json={"status": "delivered"}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        log.error(f"Failed to mark {msg_id[:8]} delivered: {e}")


# ─── Desktop automation ───────────────────────────────────────────────
def type_into_cowork(text):
    """Find Cowork window and type message into chat box."""
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        log.error("Missing deps. Run: pip install pyautogui pygetwindow")
        return False

    # Find window
    windows = gw.getWindowsWithTitle(COWORK_WINDOW_TITLE)
    if not windows:
        for alt in ["Cowork", "Claude Desktop", "Claude.ai"]:
            windows = gw.getWindowsWithTitle(alt)
            if windows:
                break

    if not windows:
        log.error("Could not find Cowork/Claude window. Is the app open?")
        return False

    win = windows[0]

    try:
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.5)
    except Exception as e:
        log.warning(f"Could not activate window: {e}")

    # Click chat input (center-bottom of window)
    input_x = win.left + (win.width // 2)
    input_y = win.top + win.height - 80
    pyautogui.click(input_x, input_y)
    time.sleep(0.3)

    # Type short nudge only — CL uses check_inbox MCP tool for full content
    pyautogui.write(text, interval=0.02)
    time.sleep(0.5)
    pyautogui.press("enter")

    return True


def format_for_chat(msg):
    """Short nudge only — CL uses check_inbox MCP tool for full content."""
    from_agent = msg["from_agent"]
    msg_id = msg["id"][:8]
    channel = "response" if msg.get("channel") == "inbox" else "command"
    content_preview = msg["content"][:80].replace("\n", " ")
    return f"New {channel} from {from_agent} ({msg_id}): {content_preview}... Run check_inbox for full content."


# ─── Main loop ────────────────────────────────────────────────────────
def main():
    log.info(f"CL Listener started — polling every {POLL_INTERVAL}s")
    log.info(f"Watching for responses to agent: {AGENT_ID}")
    log.info("Press Ctrl+C to stop.\n")

    consecutive_errors = 0

    while True:
        try:
            # Check both: responses from agents AND commands sent to CL
            responses = fetch_new_responses()
            commands = fetch_commands_for_me()
            all_messages = responses + commands
            consecutive_errors = 0

            if all_messages:
                log.info(f"Found {len(all_messages)} new message(s)!")

                for msg in all_messages:
                    msg_id = msg["id"]
                    short_id = msg_id[:8]
                    log.info(f"  [{short_id}] from {msg['from_agent']}: {msg['content'][:80]}...")

                    mark_delivered(msg_id)

                    chat_text = format_for_chat(msg)
                    success = type_into_cowork(chat_text)

                    if success:
                        log.info(f"  [{short_id}] Typed into Cowork")
                    else:
                        log.warning(f"  [{short_id}] Could not type into Cowork")
                        log.warning(f"  Content: {msg['content']}")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("\nShutting down CL Listener.")
            sys.exit(0)

        except Exception as e:
            consecutive_errors += 1
            log.error(f"Unexpected error: {e}")

            if consecutive_errors >= 5:
                backoff = min(300, POLL_INTERVAL * consecutive_errors)
                log.warning(f"  {consecutive_errors} errors — backing off {backoff}s")
                time.sleep(backoff)
            else:
                time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
