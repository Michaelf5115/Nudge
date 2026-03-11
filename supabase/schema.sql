-- TextApp schema
-- Run this in Supabase SQL editor to initialize the database

-- Teams: one per company, owns a dedicated Twilio number
CREATE TABLE IF NOT EXISTS teams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  phone_number TEXT NOT NULL UNIQUE,   -- The Twilio number assigned to this team
  admin_phone TEXT,                    -- Phone number of the person who set it up
  admin_email TEXT,                    -- Email for magic link dashboard access
  timezone TEXT NOT NULL DEFAULT 'America/New_York',
  digest_hour INTEGER NOT NULL DEFAULT 8, -- Local hour to send morning digest
  setup_complete BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users: team members identified by their phone number
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone_number TEXT NOT NULL,
  joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(team_id, phone_number)
);

-- Tasks: the core work item
CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  owner_id UUID REFERENCES users(id) ON DELETE SET NULL,    -- Who is responsible
  created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'blocked')),
  due_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Messages: full log of every SMS in and out
CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- LLM cost tracking (log every Haiku call)
CREATE TABLE IF NOT EXISTS llm_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  intent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Magic link tokens for dashboard access
CREATE TABLE IF NOT EXISTS magic_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  token TEXT NOT NULL UNIQUE,
  used BOOLEAN NOT NULL DEFAULT FALSE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Pending invites: phone numbers invited but not yet texted "join"
CREATE TABLE IF NOT EXISTS pending_invites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  phone_number TEXT NOT NULL,
  name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(team_id, phone_number)
);

-- Early-access waitlist
CREATE TABLE IF NOT EXISTS waitlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for hot paths
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number);
CREATE INDEX IF NOT EXISTS idx_tasks_team_status ON tasks(team_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_id);
CREATE INDEX IF NOT EXISTS idx_messages_team_user ON messages(team_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_teams_phone ON teams(phone_number);

-- ──────────────────────────────────────────────────────────────────
-- Row Level Security
-- All DB access goes through our server (service role or anon key
-- server-side only). RLS ensures that even if the anon key leaked,
-- a direct Supabase client could not read or write any data.
-- ──────────────────────────────────────────────────────────────────

ALTER TABLE teams           ENABLE ROW LEVEL SECURITY;
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks           ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages        ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE magic_tokens    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE waitlist        ENABLE ROW LEVEL SECURITY;

-- No access via anon key at all — our server uses the service role key
-- (set SUPABASE_SERVICE_ROLE_KEY in env and use createClient with it).
-- The policies below explicitly deny everything from the anon role.

CREATE POLICY "deny anon read teams"           ON teams           FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read users"           ON users           FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read tasks"           ON tasks           FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read messages"        ON messages        FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read llm_logs"        ON llm_logs        FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read magic_tokens"    ON magic_tokens    FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read pending_invites" ON pending_invites FOR ALL TO anon USING (false);
CREATE POLICY "deny anon read waitlist"        ON waitlist        FOR ALL TO anon USING (false);
