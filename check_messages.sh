#!/bin/bash
# Agent Comm — Check & pull unread commands for this agent
# Usage: ./check_messages.sh <agent_id>
# Example: ./check_messages.sh CE
#
# Returns unread commands, then marks them as 'delivered'

SUPABASE_URL="${AGENTCOMM_URL:-https://YOUR_PROJECT.supabase.co}"
SUPABASE_KEY="${AGENTCOMM_KEY:-YOUR_ANON_KEY}"

AGENT_ID="${1:?Usage: check_messages.sh <agent_id>}"

# Pull unread commands for this agent
RESPONSE=$(curl -s "${SUPABASE_URL}/rest/v1/messages?to_agent=eq.${AGENT_ID}&channel=eq.command&status=eq.sent&order=created_at.asc" \
  -H "apikey: ${SUPABASE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_KEY}")

# Count messages
COUNT=$(echo "$RESPONSE" | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d))" 2>/dev/null || echo "0")

if [ "$COUNT" = "0" ]; then
  echo "No new commands for ${AGENT_ID}."
  exit 0
fi

echo "=== ${COUNT} new command(s) for ${AGENT_ID} ==="
echo ""

# Display each message
echo "$RESPONSE" | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
for i, m in enumerate(msgs, 1):
    print(f'--- Command {i} ---')
    print(f'  ID:   {m[\"id\"]}')
    print(f'  From: {m[\"from_agent\"]}')
    print(f'  Time: {m[\"created_at\"]}')
    print(f'  Content:')
    for line in m['content'].split('\n'):
        print(f'    {line}')
    print()
"

# Mark all as delivered
IDS=$(echo "$RESPONSE" | python3 -c "
import json, sys
msgs = json.load(sys.stdin)
print(','.join(m['id'] for m in msgs))
")

for ID in $(echo "$IDS" | tr ',' ' '); do
  curl -s -X PATCH "${SUPABASE_URL}/rest/v1/messages?id=eq.${ID}" \
    -H "apikey: ${SUPABASE_KEY}" \
    -H "Authorization: Bearer ${SUPABASE_KEY}" \
    -H "Content-Type: application/json" \
    -H "Prefer: return=minimal" \
    -d '{"status":"delivered"}'
done

echo "✓ All marked as delivered."
