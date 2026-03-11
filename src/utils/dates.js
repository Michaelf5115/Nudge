/**
 * Format a due date for display in SMS.
 * "2025-03-14" → "Friday Mar 14"
 */
function formatDueDate(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr + 'T12:00:00Z'); // noon UTC to avoid timezone edge cases
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
}

/**
 * Is a date string today or in the past?
 */
function isOverdue(dateStr) {
  if (!dateStr) return false;
  const today = new Date().toISOString().split('T')[0];
  return dateStr < today;
}

/**
 * Is a date string today?
 */
function isToday(dateStr) {
  if (!dateStr) return false;
  const today = new Date().toISOString().split('T')[0];
  return dateStr === today;
}

module.exports = { formatDueDate, isOverdue, isToday };
