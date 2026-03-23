"""
AI Service Layer — core/services/ai_service.py

This module is the brain of Nudge. It orchestrates all interactions with
Claude, maintains conversation context, and routes tool calls to the
appropriate handlers in tools.py.

Full implementation will use the Anthropic Python SDK with tool use (function
calling). The stubs below define the expected signatures, docstrings, and
return shapes so that the rest of the codebase can be wired up immediately.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)


# ─── Tool definitions for Claude ─────────────────────────────────────────────
# Passed to the Anthropic API as the `tools` parameter so Claude knows which
# actions it can take on behalf of the user.

TOOL_DEFINITIONS = [
    # Task tools
    {
        "name": "create_task",
        "description": "Create a new task inside a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "assignee_id": {"type": "integer"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "due_date": {"type": "string", "description": "ISO 8601 date"},
            },
            "required": ["project_id", "title"],
        },
    },
    {
        "name": "update_task",
        "description": "Update fields on an existing task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "blocked", "done"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "due_date": {"type": "string"},
                "assignee_id": {"type": "integer"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as done.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "assign_task",
        "description": "Assign a task to a team member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "assignee_id": {"type": "integer"},
            },
            "required": ["task_id", "assignee_id"],
        },
    },
    {
        "name": "add_task_note",
        "description": "Add a comment or note to an existing task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "message": {"type": "string"},
            },
            "required": ["task_id", "message"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    # Project tools
    {
        "name": "create_project",
        "description": "Create a new project for a team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "start_date": {"type": "string"},
                "due_date": {"type": "string"},
            },
            "required": ["team_id", "name"],
        },
    },
    {
        "name": "update_project",
        "description": "Update fields on an existing project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "on_hold", "completed", "cancelled"]},
                "due_date": {"type": "string"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "delete_project",
        "description": "Delete a project by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"project_id": {"type": "integer"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "generate_project_summary",
        "description": "Generate a natural language summary of a project's current state.",
        "input_schema": {
            "type": "object",
            "properties": {"project_id": {"type": "integer"}},
            "required": ["project_id"],
        },
    },
    # Check-in / nudge tools
    {
        "name": "poke_user",
        "description": "Send a nudge to a user who has stale tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "check_up_for_user",
        "description": "Run a proactive check-in for a user, reviewing their open tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "update_manager",
        "description": "Generate a team status digest for a manager.",
        "input_schema": {
            "type": "object",
            "properties": {"manager_id": {"type": "integer"}},
            "required": ["manager_id"],
        },
    },
]


# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Nudge, an AI project management assistant embedded in a team's workflow.

Your responsibilities:
1. Interpret natural language messages from team members and translate them into structured project management actions (create/update tasks, log status changes, etc.).
2. Proactively identify blockers, missed deadlines, and team bottlenecks.
3. Generate concise status summaries for managers and stakeholders.
4. Keep the project knowledge repository up to date with important decisions and context.

Guidelines:
- Always be concise and action-oriented. Confirm what you did, not what you're about to do.
- When a message is ambiguous, make the most reasonable interpretation and note your assumption.
- Never fabricate task IDs or user names — only reference entities that exist in the context provided.
- If you cannot complete an action (missing information, ambiguous intent), explain clearly and ask one focused follow-up question.
"""


# ─── Main entry point ─────────────────────────────────────────────────────────


def interpret_user_message(user_id: int, message: str) -> dict[str, Any]:
    """
    Main AI entry point. Processes a natural language message from a user and
    takes appropriate project management actions via Claude tool calls.

    Flow:
      1. Fetch the user from the DB.
      2. Build a rich context object (tasks, projects, recent messages, RAG results).
      3. Call Claude with the system prompt, context, message, and tool definitions.
      4. If Claude returns tool calls, execute them via handle_tool_call().
      5. Optionally loop back to Claude with tool results for a final response.
      6. Return the structured result dict.

    Args:
        user_id: PK of the User who sent the message.
        message:  The raw natural language message text.

    Returns:
        {
            "success": bool,
            "response": str,          # Claude's natural language reply
            "actions_taken": list,    # list of tool call results
            "error": str | None,
        }
    """
    from ..models import User

    logger.info("interpret_user_message: user_id=%s", user_id)

    try:
        user = User.objects.select_related("team").get(pk=user_id)
    except User.DoesNotExist:
        return {"success": False, "response": "", "error": f"User {user_id} not found."}

    context = build_context(user)

    # TODO: Replace with real Anthropic API call
    ai_response = call_claude(
        system_prompt=SYSTEM_PROMPT,
        context=context,
        message=message,
    )

    actions_taken = []
    response_text = ai_response.get("response", "")

    # Process any tool calls Claude returned
    for tool_call in ai_response.get("tool_calls", []):
        tool_result = handle_tool_call(
            tool_name=tool_call["name"],
            params=tool_call["input"],
            user=user,
        )
        actions_taken.append({"tool": tool_call["name"], "result": tool_result})

    return {
        "success": True,
        "response": response_text,
        "actions_taken": actions_taken,
    }


# ─── Context builder ──────────────────────────────────────────────────────────


def build_context(user) -> dict[str, Any]:
    """
    Assemble a rich context object for the AI. This is passed alongside the
    user's message so Claude has full situational awareness.

    Retrieves:
    - User profile and role
    - Open tasks assigned to the user (ordered by priority/due_date)
    - Active projects for the user's team
    - The 10 most recent conversation messages in the user's team
    - Semantically similar past messages (via pgvector cosine search)
    - Recent ProjectKnowledge entries for relevant projects

    Args:
        user: The core.User ORM instance.

    Returns:
        A dict that will be serialised to JSON and injected into the
        Claude system/user prompt as structured context.
    """
    from ..models import ConversationMessage, Project, ProjectKnowledge, Task
    from ..utils.vector_search import get_similar_messages

    context: dict[str, Any] = {}

    # User profile
    context["user"] = {
        "id": user.pk,
        "name": user.name or user.username,
        "role": user.role,
        "team_id": user.team_id,
        "team_name": user.team.name if user.team else None,
    }

    # Open tasks for this user
    open_tasks = Task.objects.filter(
        assignee=user,
    ).exclude(
        status=Task.Status.DONE,
    ).select_related("project").order_by("due_date", "-priority")[:20]

    context["open_tasks"] = [
        {
            "id": t.pk,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "project": t.project.name,
            "project_id": t.project_id,
        }
        for t in open_tasks
    ]

    # Active projects in this team
    if user.team_id:
        projects = Project.objects.filter(
            team_id=user.team_id,
            status=Project.Status.ACTIVE,
        )[:10]
        context["active_projects"] = [
            {
                "id": p.pk,
                "name": p.name,
                "status": p.status,
                "due_date": p.due_date.isoformat() if p.due_date else None,
            }
            for p in projects
        ]
    else:
        context["active_projects"] = []

    # Recent conversation messages in this team
    if user.team_id:
        recent_messages = (
            ConversationMessage.objects.filter(team_id=user.team_id)
            .select_related("user")
            .order_by("-timestamp")[:10]
        )
        context["recent_messages"] = [
            {
                "id": m.pk,
                "user": m.user.name or m.user.username,
                "text": m.message_text,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in recent_messages
        ]
    else:
        context["recent_messages"] = []

    # TODO: Generate embedding for the current message and run vector search
    # query_embedding = embed_text(current_message)
    # similar = get_similar_messages(query_embedding, team_id=user.team_id)
    # context["similar_messages"] = similar
    context["similar_messages"] = []  # Placeholder until embedding step is wired in

    return context


# ─── Claude API call ──────────────────────────────────────────────────────────


def call_claude(
    system_prompt: str,
    context: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    """
    Make an API call to Claude (Anthropic) using the messages API with tool use.

    This function constructs the full request payload — system prompt, context
    injected as a structured assistant-turn preamble, the user's message, and
    the list of available tools — then sends it to the Anthropic API.

    Args:
        system_prompt: The high-level instructions for Claude's behaviour.
        context:       Structured context dict produced by build_context().
        message:       The raw user message to interpret.

    Returns:
        {
            "response": str,       # Claude's text response (may be empty if only tool calls)
            "tool_calls": list,    # List of {"name": str, "input": dict} dicts
            "stop_reason": str,    # "end_turn" | "tool_use" | "max_tokens"
        }

    Full implementation (replace the stub below):
        import anthropic, json
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Context:\\n{json.dumps(context, indent=2)}\\n\\n"
                        f"Message: {message}"
                    ),
                }
            ],
        )
        tool_calls = [
            {"name": b.name, "input": b.input}
            for b in response.content
            if b.type == "tool_use"
        ]
        text = " ".join(b.text for b in response.content if b.type == "text")
        return {"response": text, "tool_calls": tool_calls, "stop_reason": response.stop_reason}
    """
    import json

    logger.debug("call_claude: message=%r context_keys=%s", message[:80], list(context.keys()))

    # ── STUB ── Replace with real Anthropic SDK call above ──
    return {
        "response": (
            f"[STUB] Received message from user {context.get('user', {}).get('name', 'unknown')}: "
            f'"{message}". AI pipeline not yet connected.'
        ),
        "tool_calls": [],
        "stop_reason": "end_turn",
    }


# ─── Tool call router ─────────────────────────────────────────────────────────


def handle_tool_call(
    tool_name: str,
    params: dict[str, Any],
    user,
) -> dict[str, Any]:
    """
    Route a tool call returned by Claude to the appropriate handler function
    in core/services/tools.py.

    Each handler receives the raw params dict from Claude plus the acting user
    so that audit records (TaskUpdate, etc.) can be attributed correctly.

    Args:
        tool_name: The name of the tool Claude wants to invoke.
        params:    The input dict Claude provided for the tool.
        user:      The core.User on whose behalf the action is being taken.

    Returns:
        A dict with at minimum {"success": bool, "message": str} plus any
        additional data returned by the specific tool handler.
    """
    from . import tools

    TOOL_REGISTRY = {
        # Task tools
        "create_task": tools.create_task,
        "update_task": tools.update_task,
        "delete_task": tools.delete_task,
        "complete_task": tools.complete_task,
        "assign_task": tools.assign_task,
        "add_task_note": tools.add_task_note,
        # Project tools
        "create_project": tools.create_project,
        "update_project": tools.update_project,
        "delete_project": tools.delete_project,
        "generate_project_summary": tools.generate_project_summary,
        # Check-in tools
        "poke_user": tools.poke_user,
        "check_up_for_user": tools.check_up_for_user,
        "update_manager": tools.update_manager,
    }

    handler = TOOL_REGISTRY.get(tool_name)
    if not handler:
        logger.warning("handle_tool_call: unknown tool '%s'", tool_name)
        return {"success": False, "message": f"Unknown tool: {tool_name}"}

    try:
        return handler(params, user)
    except Exception as exc:
        logger.exception("handle_tool_call: error in tool '%s': %s", tool_name, exc)
        return {"success": False, "message": str(exc)}


# ─── Proactive AI triggers ────────────────────────────────────────────────────


def check_up_for_user(user) -> dict[str, Any]:
    """
    Proactive check-in for a user. Reviews their open tasks and generates a
    status prompt if there are overdue items or upcoming deadlines.

    Called by the scheduler (Celery beat) or triggered manually via the API.

    Args:
        user: The core.User ORM instance to check in on.

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    logger.info("check_up_for_user: user_id=%s", user.pk)

    context = build_context(user)
    message = (
        "Please review this user's open tasks and generate a brief, friendly "
        "check-in message asking for a status update on any overdue or high-priority items."
    )

    # TODO: Call Claude and optionally dispatch the response via the user's preferred channel
    result = call_claude(SYSTEM_PROMPT, context, message)

    return {
        "success": True,
        "message": result["response"],
        "data": {"user_id": user.pk, "open_task_count": len(context.get("open_tasks", []))},
    }


def poke_user(user) -> dict[str, Any]:
    """
    Send a nudge to a user who has stale tasks or missed next_nudge_date.

    More direct than check_up_for_user — used when the system detects that
    a task has not been updated in a significant amount of time.

    Args:
        user: The core.User ORM instance to poke.

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    from ..models import Task
    import datetime

    logger.info("poke_user: user_id=%s", user.pk)

    stale_threshold = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=3)
    stale_tasks = Task.objects.filter(
        assignee=user,
        last_updated__lt=stale_threshold,
    ).exclude(status=Task.Status.DONE)

    context = build_context(user)
    context["stale_tasks"] = [
        {"id": t.pk, "title": t.title, "last_updated": t.last_updated.isoformat()}
        for t in stale_tasks[:5]
    ]

    message = (
        "This user has tasks that haven't been updated in several days. "
        "Generate a short, friendly poke message urging them to post a status update."
    )

    # TODO: Dispatch via user's preferred channel (Teams, Slack, SMS, etc.)
    result = call_claude(SYSTEM_PROMPT, context, message)

    return {
        "success": True,
        "message": result["response"],
        "data": {"user_id": user.pk, "stale_task_count": stale_tasks.count()},
    }


def update_manager(manager) -> dict[str, Any]:
    """
    Generate a team status digest for a manager covering all active projects,
    overdue tasks, blockers, and recent team activity.

    Args:
        manager: The core.User ORM instance (must have role=manager).

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    from ..models import Project, Task

    logger.info("update_manager: manager_id=%s", manager.pk)

    managed_teams = manager.managed_teams.prefetch_related("members").all()
    team_ids = list(managed_teams.values_list("id", flat=True))

    active_projects = Project.objects.filter(
        team_id__in=team_ids,
        status=Project.Status.ACTIVE,
    ).select_related("team")[:10]

    blocked_tasks = Task.objects.filter(
        project__team_id__in=team_ids,
        status=Task.Status.BLOCKED,
    ).select_related("assignee", "project")[:10]

    context = build_context(manager)
    context["managed_teams"] = [{"id": t.pk, "name": t.name} for t in managed_teams]
    context["active_projects"] = [
        {
            "id": p.pk,
            "name": p.name,
            "team": p.team.name,
            "due_date": p.due_date.isoformat() if p.due_date else None,
        }
        for p in active_projects
    ]
    context["blocked_tasks"] = [
        {
            "id": t.pk,
            "title": t.title,
            "project": t.project.name,
            "assignee": str(t.assignee) if t.assignee else "unassigned",
        }
        for t in blocked_tasks
    ]

    message = (
        "Generate a concise manager status digest covering active projects, "
        "any blockers, overdue tasks, and a brief team health assessment."
    )

    result = call_claude(SYSTEM_PROMPT, context, message)

    return {
        "success": True,
        "message": result["response"],
        "data": {
            "manager_id": manager.pk,
            "active_project_count": len(context["active_projects"]),
            "blocked_task_count": len(context["blocked_tasks"]),
        },
    }


def generate_project_summary(project) -> dict[str, Any]:
    """
    Generate a human-readable project summary using the project's tasks,
    recent activity, and knowledge repository (RAG).

    Args:
        project: The core.Project ORM instance.

    Returns:
        {"success": bool, "summary": str, "data": dict}
    """
    from ..models import ProjectKnowledge, Task

    logger.info("generate_project_summary: project_id=%s", project.pk)

    tasks = Task.objects.filter(project=project).select_related("assignee")
    knowledge = ProjectKnowledge.objects.filter(project=project).order_by("-created_at")[:10]

    task_stats = {
        "total": tasks.count(),
        "todo": tasks.filter(status=Task.Status.TODO).count(),
        "in_progress": tasks.filter(status=Task.Status.IN_PROGRESS).count(),
        "blocked": tasks.filter(status=Task.Status.BLOCKED).count(),
        "done": tasks.filter(status=Task.Status.DONE).count(),
    }

    context = {
        "project": {
            "id": project.pk,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "due_date": project.due_date.isoformat() if project.due_date else None,
        },
        "task_stats": task_stats,
        "knowledge_snippets": [k.content for k in knowledge],
    }

    message = (
        "Generate a concise, professional project status summary. "
        "Include overall health, key risks, and recommended next actions."
    )

    result = call_claude(SYSTEM_PROMPT, context, message)

    return {
        "success": True,
        "summary": result["response"],
        "data": {"project_id": project.pk, "task_stats": task_stats},
    }
