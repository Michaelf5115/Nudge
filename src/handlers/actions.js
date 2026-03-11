/**
 * Task action handlers.
 * Each function returns a human-friendly SMS reply string.
 */

const db = require('../db');
const { formatDueDate } = require('../utils/dates');

// ------------------------------------------------------------------
// CREATE
// ------------------------------------------------------------------

async function handleCreate(parsed, team, user) {
  const { task_title, owner_name, due_date } = parsed;

  if (!task_title) {
    return "What's the task? Try: \"Add task: write Q1 report\"";
  }

  // Resolve owner
  let owner = null;
  if (owner_name) {
    const matches = await db.findUserByNameInTeam(team.id, owner_name);
    if (matches.length === 1) {
      owner = matches[0];
    } else if (matches.length > 1) {
      return `Found multiple people named "${owner_name}". Can you be more specific?`;
    } else {
      return `I don't know anyone named "${owner_name}" on your team. Have them text this number first to join.`;
    }
  }

  const task = await db.createTask({
    teamId: team.id,
    ownerId: owner ? owner.id : user.id,
    createdById: user.id,
    title: task_title,
    dueDate: due_date || null,
  });

  const ownerName = owner ? owner.name : user.name;
  const duePart = due_date ? `, due ${formatDueDate(due_date)}` : '';
  return `Done — "${task_title}" assigned to ${ownerName}${duePart}.`;
}

// ------------------------------------------------------------------
// UPDATE STATUS
// ------------------------------------------------------------------

async function handleUpdate(parsed, team, user) {
  const { task_title, new_status, due_date } = parsed;

  if (!task_title) {
    return "Which task? Try: \"Mark homepage copy as done\"";
  }

  const tasks = await db.searchTasks(team.id, task_title);
  if (tasks.length === 0) {
    return `I couldn't find a task matching "${task_title}". Try again with a few keywords.`;
  }
  if (tasks.length > 1) {
    const list = tasks.slice(0, 3).map((t, i) => `${i + 1}. ${t.title}`).join('\n');
    return `Found multiple tasks:\n${list}\n\nBe more specific.`;
  }

  const task = tasks[0];
  const updates = {};
  if (new_status) updates.status = new_status;
  if (due_date) updates.due_date = due_date;

  if (Object.keys(updates).length === 0) {
    return "What should I update? You can change the status (done/blocked/open) or due date.";
  }

  await db.updateTask(task.id, team.id, updates);

  const statusEmoji = { done: '✓', blocked: '⚠', open: '○' }[new_status] || '';
  if (new_status === 'done') {
    return `${statusEmoji} Marked "${task.title}" as done. Nice work!`;
  } else if (new_status === 'blocked') {
    return `${statusEmoji} "${task.title}" marked as blocked. Loop in your team?`;
  } else if (due_date) {
    return `Updated — "${task.title}" now due ${formatDueDate(due_date)}.`;
  }
  return `Updated "${task.title}".`;
}

// ------------------------------------------------------------------
// ASSIGN
// ------------------------------------------------------------------

async function handleAssign(parsed, team, user) {
  const { task_title, owner_name } = parsed;

  if (!task_title) return "Which task do you want to reassign?";
  if (!owner_name) return "Who do you want to assign it to?";

  const tasks = await db.searchTasks(team.id, task_title);
  if (tasks.length === 0) return `Can't find a task matching "${task_title}".`;
  if (tasks.length > 1) {
    const list = tasks.slice(0, 3).map((t, i) => `${i + 1}. ${t.title}`).join('\n');
    return `Multiple matches:\n${list}\n\nBe more specific.`;
  }

  const matches = await db.findUserByNameInTeam(team.id, owner_name);
  if (matches.length === 0) return `"${owner_name}" isn't on your team yet.`;
  if (matches.length > 1) return `Multiple people named "${owner_name}". Who exactly?`;

  const task = tasks[0];
  const newOwner = matches[0];
  await db.updateTask(task.id, team.id, { owner_id: newOwner.id });

  return `Done — "${task.title}" reassigned to ${newOwner.name}.`;
}

// ------------------------------------------------------------------
// QUERY
// ------------------------------------------------------------------

async function handleQuery(parsed, team, user) {
  const { query_target } = parsed;

  let targetUser = user;
  let label = 'Your';

  if (query_target && query_target !== 'me') {
    if (query_target === 'all') {
      return await handleQueryAll(team);
    }
    const matches = await db.findUserByNameInTeam(team.id, query_target);
    if (matches.length === 0) return `"${query_target}" isn't on your team.`;
    if (matches.length > 1) return `Multiple people named "${query_target}". Be more specific.`;
    targetUser = matches[0];
    label = `${targetUser.name}'s`;
  }

  const tasks = await db.getOpenTasksForUser(targetUser.id);
  if (tasks.length === 0) return `${label} task list is empty — all clear!`;

  const lines = tasks.map(t => {
    const due = t.due_date ? ` (${formatDueDate(t.due_date)})` : '';
    const status = t.status === 'blocked' ? ' ⚠' : '';
    return `• ${t.title}${due}${status}`;
  });

  return `${label} open tasks:\n${lines.join('\n')}`;
}

async function handleQueryAll(team) {
  const tasks = await db.getTeamTasks(team.id, 'open');
  if (tasks.length === 0) return 'No open tasks — the team is all clear!';

  // Group by owner
  const byOwner = {};
  for (const t of tasks) {
    const name = t.owner?.name || 'Unassigned';
    if (!byOwner[name]) byOwner[name] = [];
    byOwner[name].push(t);
  }

  const sections = Object.entries(byOwner).map(([name, ts]) => {
    const lines = ts.map(t => {
      const due = t.due_date ? ` (${formatDueDate(t.due_date)})` : '';
      return `  • ${t.title}${due}`;
    });
    return `${name}:\n${lines.join('\n')}`;
  });

  return `Team tasks:\n\n${sections.join('\n\n')}`;
}

module.exports = { handleCreate, handleUpdate, handleAssign, handleQuery };
