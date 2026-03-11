const { createClient } = require('@supabase/supabase-js');

// Use service role key server-side so RLS doesn't block our own queries.
// The anon key is only for client-side use (we don't expose it to browsers).
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY
);

// In-memory cache for team/user lookups (cleared every 5 min)
const cache = new Map();
const CACHE_TTL = 5 * 60 * 1000;

function cacheSet(key, value) {
  cache.set(key, { value, expires: Date.now() + CACHE_TTL });
}

function cacheGet(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() > entry.expires) { cache.delete(key); return null; }
  return entry.value;
}

function cacheDel(key) {
  cache.delete(key);
}

// ------------------------------------------------------------------
// Teams
// ------------------------------------------------------------------

async function getTeamByPhoneNumber(phoneNumber) {
  const key = `team:phone:${phoneNumber}`;
  const cached = cacheGet(key);
  if (cached) return cached;

  const { data, error } = await supabase
    .from('teams')
    .select('*')
    .eq('phone_number', phoneNumber)
    .single();

  if (error || !data) return null;
  cacheSet(key, data);
  return data;
}

async function createTeam({ name, phoneNumber, adminPhone, timezone = 'America/New_York' }) {
  const { data, error } = await supabase
    .from('teams')
    .insert({ name, phone_number: phoneNumber, admin_phone: adminPhone, timezone })
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function updateTeam(teamId, updates) {
  cacheDel(`team:id:${teamId}`);
  const { data, error } = await supabase
    .from('teams')
    .update(updates)
    .eq('id', teamId)
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function getTeamById(teamId) {
  const key = `team:id:${teamId}`;
  const cached = cacheGet(key);
  if (cached) return cached;

  const { data, error } = await supabase
    .from('teams')
    .select('*')
    .eq('id', teamId)
    .single();

  if (error || !data) return null;
  cacheSet(key, data);
  return data;
}

async function getAllTeams() {
  const { data, error } = await supabase.from('teams').select('*');
  if (error) throw error;
  return data || [];
}

// ------------------------------------------------------------------
// Users
// ------------------------------------------------------------------

async function getUserByPhone(teamId, phoneNumber) {
  const key = `user:${teamId}:${phoneNumber}`;
  const cached = cacheGet(key);
  if (cached) return cached;

  const { data, error } = await supabase
    .from('users')
    .select('*')
    .eq('team_id', teamId)
    .eq('phone_number', phoneNumber)
    .single();

  if (error || !data) return null;
  cacheSet(key, data);
  return data;
}

async function getUserById(userId) {
  const key = `user:id:${userId}`;
  const cached = cacheGet(key);
  if (cached) return cached;

  const { data, error } = await supabase
    .from('users')
    .select('*')
    .eq('id', userId)
    .single();

  if (error || !data) return null;
  cacheSet(key, data);
  return data;
}

async function getTeamUsers(teamId) {
  const { data, error } = await supabase
    .from('users')
    .select('*')
    .eq('team_id', teamId)
    .order('joined_at');

  if (error) throw error;
  return data || [];
}

async function createUser({ teamId, name, phoneNumber }) {
  const { data, error } = await supabase
    .from('users')
    .insert({ team_id: teamId, name, phone_number: phoneNumber })
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function findUserByNameInTeam(teamId, namePart) {
  const { data, error } = await supabase
    .from('users')
    .select('*')
    .eq('team_id', teamId)
    .ilike('name', `%${namePart}%`);

  if (error) return [];
  return data || [];
}

// ------------------------------------------------------------------
// Tasks
// ------------------------------------------------------------------

async function createTask({ teamId, ownerId, createdById, title, dueDate }) {
  const { data, error } = await supabase
    .from('tasks')
    .insert({
      team_id: teamId,
      owner_id: ownerId || null,
      created_by_id: createdById,
      title,
      due_date: dueDate || null,
      status: 'open',
    })
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function getOpenTasksForUser(userId) {
  const { data, error } = await supabase
    .from('tasks')
    .select('*, owner:owner_id(name), created_by:created_by_id(name)')
    .eq('owner_id', userId)
    .eq('status', 'open')
    .order('due_date', { ascending: true, nullsFirst: false });

  if (error) throw error;
  return data || [];
}

async function getTeamTasks(teamId, status = null) {
  let query = supabase
    .from('tasks')
    .select('*, owner:owner_id(name), created_by:created_by_id(name)')
    .eq('team_id', teamId)
    .order('due_date', { ascending: true, nullsFirst: false });

  if (status) query = query.eq('status', status);

  const { data, error } = await query;
  if (error) throw error;
  return data || [];
}

async function updateTask(taskId, teamId, updates) {
  const { data, error } = await supabase
    .from('tasks')
    .update({ ...updates, updated_at: new Date().toISOString() })
    .eq('id', taskId)
    .eq('team_id', teamId)
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function searchTasks(teamId, titleQuery) {
  const { data, error } = await supabase
    .from('tasks')
    .select('*, owner:owner_id(name)')
    .eq('team_id', teamId)
    .ilike('title', `%${titleQuery}%`)
    .neq('status', 'done')
    .limit(5);

  if (error) throw error;
  return data || [];
}

// ------------------------------------------------------------------
// Messages
// ------------------------------------------------------------------

async function logMessage({ teamId, userId, direction, body }) {
  const { error } = await supabase
    .from('messages')
    .insert({ team_id: teamId, user_id: userId, direction, body });

  if (error) console.error('Failed to log message:', error.message);
}

async function getRecentMessages(teamId, userId, limit = 5) {
  const { data, error } = await supabase
    .from('messages')
    .select('direction, body, created_at')
    .eq('team_id', teamId)
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(limit);

  if (error) return [];
  return (data || []).reverse(); // oldest first
}

// ------------------------------------------------------------------
// LLM Logging
// ------------------------------------------------------------------

async function logLLMCall({ teamId, userId, inputTokens, outputTokens, intent }) {
  const { error } = await supabase
    .from('llm_logs')
    .insert({ team_id: teamId, user_id: userId, input_tokens: inputTokens, output_tokens: outputTokens, intent });

  if (error) console.error('Failed to log LLM call:', error.message);
}

// ------------------------------------------------------------------
// Magic Tokens
// ------------------------------------------------------------------

async function createMagicToken(teamId) {
  const token = require('crypto').randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

  const { data, error } = await supabase
    .from('magic_tokens')
    .insert({ team_id: teamId, token, expires_at: expiresAt })
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function validateMagicToken(token) {
  const { data, error } = await supabase
    .from('magic_tokens')
    .select('*, team:team_id(*)')
    .eq('token', token)
    .eq('used', false)
    .gt('expires_at', new Date().toISOString())
    .single();

  if (error || !data) return null;
  return data;
}

async function markTokenUsed(tokenId) {
  await supabase
    .from('magic_tokens')
    .update({ used: true })
    .eq('id', tokenId);
}

// ------------------------------------------------------------------
// Pending Invites
// ------------------------------------------------------------------

async function addPendingInvite(teamId, phoneNumber, name = null) {
  const { data, error } = await supabase
    .from('pending_invites')
    .upsert({ team_id: teamId, phone_number: phoneNumber, name }, { onConflict: 'team_id,phone_number' })
    .select()
    .single();

  if (error) throw error;
  return data;
}

async function getPendingInvite(teamId, phoneNumber) {
  const { data } = await supabase
    .from('pending_invites')
    .select('*')
    .eq('team_id', teamId)
    .eq('phone_number', phoneNumber)
    .single();

  return data || null;
}

async function deletePendingInvite(teamId, phoneNumber) {
  await supabase
    .from('pending_invites')
    .delete()
    .eq('team_id', teamId)
    .eq('phone_number', phoneNumber);
}

module.exports = {
  supabase,
  getTeamByPhoneNumber, createTeam, updateTeam, getTeamById, getAllTeams,
  getUserByPhone, getUserById, getTeamUsers, createUser, findUserByNameInTeam,
  createTask, getOpenTasksForUser, getTeamTasks, updateTask, searchTasks,
  logMessage, getRecentMessages,
  logLLMCall,
  createMagicToken, validateMagicToken, markTokenUsed,
  addPendingInvite, getPendingInvite, deletePendingInvite,
};
