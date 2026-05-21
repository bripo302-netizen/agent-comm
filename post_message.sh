#!/bin/bash
# Agent Comm — Post a message to the dashboard
# Usage: ./post_message.sh <from_agent> <message>
# Example: ./post_message.sh CE "Task-006 image pipeline is ready for review"
#
# Environment variables (set these or edit below):
#   AGENTCOMM_URL  — Supabase project URL
#   AGENTCOMM_KEY  — Supabase anon public key

SUPABASE_URL="${AGENTCOMM_URL:-https://YOUR_PROJECT.supabase.co}"
SUPABASE_KEY="${AGENTCOMM_KEY:-YOUR_ANON_KEY}"

FROM_AGENT="${1:?Usage: post_message.sh <agent_id> <message>}"
MESSAGE="${2:?Usage: post_message.sh <agent_id> <message>}"

curl -s -X POST "${SUPABASE_URL}/rest/v1/messages" \
  -H "apikey: ${SUPABASE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_KEY}" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=minimal" \
  -d "{\"from_agent\":\"${FROM_AGENT}\",\"content\":$(echo "$MESSAGE" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read().strip()))'),\"channel\":\"inbox\",\"status\":\"sent\"}"

echo ""
echo "✓ Message posted as ${FROM_AGENT}"
