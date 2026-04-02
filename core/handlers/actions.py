"""
Task action handlers — each returns a human-friendly SMS reply string.
"""
import logging

from core.models import Task, User
from core.utils import format_due_date

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# CREATE
# ------------------------------------------------------------------

def handle_create(parsed, team, user):
    task_title = parsed.get('task_title')
    owner_name = parsed.get('owner_name')
    due_date = parsed.get('due_date')

    if not task_title:
        return 'What\'s the task? Try: "Add task: write Q1 report"'

    owner = None
    if owner_name:
        matches = list(User.objects.filter(team=team, name__icontains=owner_name))
        if len(matches) == 1:
            owner = matches[0]
        elif len(matches) > 1:
            return f'Found multiple people named "{owner_name}". Can you be more specific?'
        else:
            return (
                f'I don\'t know anyone named "{owner_name}" on your team. '
                f'Have them text this number first to join.'
            )

    Task.objects.create(
        team=team,
        owner=owner or user,
        created_by=user,
        title=task_title,
        due_date=due_date or None,
        status='open',
    )

    owner_display = owner.name if owner else user.name
    due_part = f', due {format_due_date(due_date)}' if due_date else ''
    return f'Done \u2014 "{task_title}" assigned to {owner_display}{due_part}.'


# ------------------------------------------------------------------
# UPDATE STATUS / DUE DATE
# ------------------------------------------------------------------

def handle_update(parsed, team, user):
    task_title = parsed.get('task_title')
    new_status = parsed.get('new_status')
    due_date = parsed.get('due_date')

    if not task_title:
        return 'Which task? Try: "Mark homepage copy as done"'

    tasks = list(
        Task.objects.filter(team=team, title__icontains=task_title)
        .exclude(status='done')[:5]
    )
    if not tasks:
        return f'I couldn\'t find a task matching "{task_title}". Try again with a few keywords.'
    if len(tasks) > 1:
        items = '\n'.join(f'{i + 1}. {t.title}' for i, t in enumerate(tasks[:3]))
        return f'Found multiple tasks:\n{items}\n\nBe more specific.'

    task = tasks[0]
    if not new_status and not due_date:
        return 'What should I update? You can change the status (done/blocked/open) or due date.'

    if new_status:
        task.status = new_status
    if due_date:
        task.due_date = due_date
    task.save()

    status_emoji = {'done': '\u2713', 'blocked': '\u26a0', 'open': '\u25cb'}.get(new_status, '')
    if new_status == 'done':
        return f'{status_emoji} Marked "{task.title}" as done. Nice work!'
    if new_status == 'blocked':
        return f'{status_emoji} "{task.title}" marked as blocked. Loop in your team?'
    if due_date:
        return f'Updated \u2014 "{task.title}" now due {format_due_date(due_date)}.'
    return f'Updated "{task.title}".'


# ------------------------------------------------------------------
# ASSIGN
# ------------------------------------------------------------------

def handle_assign(parsed, team, user):
    task_title = parsed.get('task_title')
    owner_name = parsed.get('owner_name')

    if not task_title:
        return 'Which task do you want to reassign?'
    if not owner_name:
        return 'Who do you want to assign it to?'

    tasks = list(
        Task.objects.filter(team=team, title__icontains=task_title)
        .exclude(status='done')[:5]
    )
    if not tasks:
        return f'Can\'t find a task matching "{task_title}".'
    if len(tasks) > 1:
        items = '\n'.join(f'{i + 1}. {t.title}' for i, t in enumerate(tasks[:3]))
        return f'Multiple matches:\n{items}\n\nBe more specific.'

    matches = list(User.objects.filter(team=team, name__icontains=owner_name))
    if not matches:
        return f'"{owner_name}" isn\'t on your team yet.'
    if len(matches) > 1:
        return f'Multiple people named "{owner_name}". Who exactly?'

    task = tasks[0]
    new_owner = matches[0]
    task.owner = new_owner
    task.save()
    return f'Done \u2014 "{task.title}" reassigned to {new_owner.name}.'


# ------------------------------------------------------------------
# QUERY
# ------------------------------------------------------------------

def handle_query(parsed, team, user):
    query_target = parsed.get('query_target')

    target_user = user
    label = 'Your'

    if query_target and query_target != 'me':
        if query_target == 'all':
            return _handle_query_all(team)
        matches = list(User.objects.filter(team=team, name__icontains=query_target))
        if not matches:
            return f'"{query_target}" isn\'t on your team.'
        if len(matches) > 1:
            return f'Multiple people named "{query_target}". Be more specific.'
        target_user = matches[0]
        label = f"{target_user.name}'s"

    tasks = list(Task.objects.filter(owner=target_user, status='open').order_by('due_date'))
    if not tasks:
        return f'{label} task list is empty \u2014 all clear!'

    lines = []
    for t in tasks:
        due = f' ({format_due_date(str(t.due_date))})' if t.due_date else ''
        flag = ' \u26a0' if t.status == 'blocked' else ''
        lines.append(f'\u2022 {t.title}{due}{flag}')

    return f'{label} open tasks:\n' + '\n'.join(lines)


def _handle_query_all(team):
    tasks = list(
        Task.objects.filter(team=team, status='open')
        .select_related('owner')
        .order_by('due_date')
    )
    if not tasks:
        return 'No open tasks \u2014 the team is all clear!'

    by_owner = {}
    for t in tasks:
        name = t.owner.name if t.owner else 'Unassigned'
        by_owner.setdefault(name, []).append(t)

    sections = []
    for name, ts in by_owner.items():
        lines = []
        for t in ts:
            due = f' ({format_due_date(str(t.due_date))})' if t.due_date else ''
            lines.append(f'  \u2022 {t.title}{due}')
        sections.append(f'{name}:\n' + '\n'.join(lines))

    return 'Team tasks:\n\n' + '\n\n'.join(sections)
