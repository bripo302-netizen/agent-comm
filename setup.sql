-- Agent Comm — Supabase Table Setup
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New Query)

-- 1. Messages table
CREATE TABLE messages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  from_agent TEXT NOT NULL,
  to_agent TEXT,
  content TEXT NOT NULL,
  channel TEXT DEFAULT 'inbox' CHECK (channel IN ('inbox', 'command')),
  status TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'delivered', 'read', 'executed')),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Enable Row Level Security (required by Supabase)
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- 3. Allow all operations via anon key (personal tool, not public)
CREATE POLICY "Allow all for anon" ON messages
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- 4. Enable Realtime on messages table
ALTER PUBLICATION supabase_realtime ADD TABLE messages;

-- 5. Create index for fast agent-specific queries
CREATE INDEX idx_messages_to_agent ON messages (to_agent, status, created_at DESC);
CREATE INDEX idx_messages_from_agent ON messages (from_agent, created_at DESC);
