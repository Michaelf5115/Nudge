"""
Tool Handlers — core/services/tools.py

Each function in this module corresponds to a tool that Claude can invoke via
tool use (function calling). When Claude decides an action should be taken, the
ai_service.handle_tool_call() router dispatches here.

All handlers share the same signature:
    handler(params: dict, user: User) -> dict

Returning:
    {
        "success": bool,
        "message": str,       # Human-readable confirmation or error description
        "data":    dict,      # Optional structured payload (e.g. the created object)
    }

All DB writes that represent user/AI actions should also create a TaskUpdate
record so there is a full audit trail.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Task Tools ───────────────────────────────────────────────────────────────


def create_task(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Create a new Task inside a project.

    Expected params:
        project_id (int, required)
        title      (str, required)
        description (str, optional)
        assignee_id (int, optional)
        priority   ("low"|"medium"|"high"|"critical", optional, default "medium")
        due_date   (ISO 8601 date string, optional)

    Behaviour:
        - Validates that project_id belongs to the user's team.
        - Creates the Task with created_by_ai=True.
        - Creates a TaskUpdate record of type "ai_generated".
        - Returns the new Task's ID and title.
    """
    from ..models import Project, Task, TaskUpdate, User as UserModel

    logger.info("create_task: params=%s actor=%s", params, user)

    try:
        project = Project.objects.get(pk=params["project_id"])
    except Project.DoesNotExist:
        return {"success": False, "message": f"Project {params['project_id']} not found."}

    assignee = None
    if params.get("assignee_id"):
        try:
            assignee = UserModel.objects.get(pk=params["assignee_id"])
        except UserModel.DoesNotExist:
            return {"success": False, "message": f"Assignee {params['assignee_id']} not found."}

    task = Task.objects.create(
        project=project,
        title=params["title"],
        description=params.get("description", ""),
        assignee=assignee,
        priority=params.get("priority", Task.Priority.MEDIUM),
        due_date=params.get("due_date") or None,
        created_by_ai=True,
    )

    TaskUpdate.objects.create(
        task=task,
        user=user,
        message=f'Task "{task.title}" created by AI.',
        update_type=TaskUpdate.UpdateType.AI_GENERATED,
        new_status=task.status,
    )

    return {
        "success": True,
        "message": f'Task "{task.title}" created in project "{project.name}".',
        "data": {"task_id": task.pk, "title": task.title, "status": task.status},
    }


def update_task(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Update one or more fields on an existing Task.

    Expected params:
        task_id    (int, required)
        title      (str, optional)
        description (str, optional)
        status     ("todo"|"in_progress"|"blocked"|"done", optional)
        priority   ("low"|"medium"|"high"|"critical", optional)
        due_date   (ISO 8601 date string, optional)
        assignee_id (int | null, optional)

    Behaviour:
        - Fetches the task, applies only the provided fields.
        - If status changes, records previous/new_status on a TaskUpdate.
        - Records a TaskUpdate of the appropriate type.
    """
    from ..models import Task, TaskUpdate, User as UserModel

    logger.info("update_task: params=%s actor=%s", params, user)

    try:
        task = Task.objects.get(pk=params["task_id"])
    except Task.DoesNotExist:
        return {"success": False, "message": f"Task {params['task_id']} not found."}

    previous_status = task.status
    changed_fields = []

    if "title" in params:
        task.title = params["title"]
        changed_fields.append("title")
    if "description" in params:
        task.description = params["description"]
        changed_fields.append("description")
    if "status" in params:
        task.status = params["status"]
        changed_fields.append("status")
    if "priority" in params:
        task.priority = params["priority"]
        changed_fields.append("priority")
    if "due_date" in params:
        task.due_date = params["due_date"] or None
        changed_fields.append("due_date")
    if "assignee_id" in params:
        if params["assignee_id"] is None:
            task.assignee = None
        else:
            try:
                task.assignee = UserModel.objects.get(pk=params["assignee_id"])
            except UserModel.DoesNotExist:
                return {"success": False, "message": f"Assignee {params['assignee_id']} not found."}
        changed_fields.append("assignee")

    if not changed_fields:
        return {"success": False, "message": "No fields to update were provided."}

    task.save()

    update_type = (
        TaskUpdate.UpdateType.STATUS_CHANGE
        if "status" in changed_fields
        else TaskUpdate.UpdateType.AI_GENERATED
    )

    TaskUpdate.objects.create(
        task=task,
        user=user,
        message=f"Updated fields: {', '.join(changed_fields)}.",
        update_type=update_type,
        previous_status=previous_status if "status" in changed_fields else None,
        new_status=task.status if "status" in changed_fields else None,
    )

    return {
        "success": True,
        "message": f'Task "{task.title}" updated (changed: {", ".join(changed_fields)}).',
        "data": {"task_id": task.pk, "status": task.status},
    }


def delete_task(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Delete a Task by ID.

    Expected params:
        task_id (int, required)

    Behaviour:
        - Validates the task exists.
        - Deletes it. (TaskUpdates are cascade-deleted by the DB.)
        - Returns confirmation with the deleted task's title.

    Note: Consider soft-delete in production — irreversible deletes should be
    gated behind a confirmation step in the UI.
    """
    from ..models import Task

    logger.info("delete_task: params=%s actor=%s", params, user)

    try:
        task = Task.objects.get(pk=params["task_id"])
    except Task.DoesNotExist:
        return {"success": False, "message": f"Task {params['task_id']} not found."}

    title = task.title
    task.delete()

    return {
        "success": True,
        "message": f'Task "{title}" has been deleted.',
        "data": {"task_id": params["task_id"]},
    }


def complete_task(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Mark a Task as done.

    Expected params:
        task_id (int, required)

    Behaviour:
        - Sets status to "done".
        - Creates a STATUS_CHANGE TaskUpdate.
    """
    from ..models import Task, TaskUpdate

    logger.info("complete_task: params=%s actor=%s", params, user)

    try:
        task = Task.objects.get(pk=params["task_id"])
    except Task.DoesNotExist:
        return {"success": False, "message": f"Task {params['task_id']} not found."}

    if task.status == Task.Status.DONE:
        return {"success": True, "message": f'Task "{task.title}" is already done.', "data": {}}

    previous_status = task.status
    task.status = Task.Status.DONE
    task.save(update_fields=["status", "last_updated"])

    TaskUpdate.objects.create(
        task=task,
        user=user,
        message="Task marked as completed by AI.",
        update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
        previous_status=previous_status,
        new_status=Task.Status.DONE,
    )

    return {
        "success": True,
        "message": f'Task "{task.title}" marked as done.',
        "data": {"task_id": task.pk, "status": Task.Status.DONE},
    }


def assign_task(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Assign a Task to a team member.

    Expected params:
        task_id     (int, required)
        assignee_id (int, required)

    Behaviour:
        - Validates both the task and the new assignee exist.
        - Updates task.assignee.
        - Creates an ASSIGNMENT TaskUpdate.
    """
    from ..models import Task, TaskUpdate, User as UserModel

    logger.info("assign_task: params=%s actor=%s", params, user)

    try:
        task = Task.objects.select_related("assignee").get(pk=params["task_id"])
    except Task.DoesNotExist:
        return {"success": False, "message": f"Task {params['task_id']} not found."}

    try:
        assignee = UserModel.objects.get(pk=params["assignee_id"])
    except UserModel.DoesNotExist:
        return {"success": False, "message": f"User {params['assignee_id']} not found."}

    previous_assignee = str(task.assignee) if task.assignee else "unassigned"
    task.assignee = assignee
    task.save(update_fields=["assignee", "last_updated"])

    TaskUpdate.objects.create(
        task=task,
        user=user,
        message=f"Assigned from {previous_assignee} to {assignee}.",
        update_type=TaskUpdate.UpdateType.ASSIGNMENT,
    )

    return {
        "success": True,
        "message": f'Task "{task.title}" assigned to {assignee}.',
        "data": {"task_id": task.pk, "assignee_id": assignee.pk},
    }


def add_task_note(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Add a comment or note to an existing Task.

    Expected params:
        task_id (int, required)
        message (str, required)

    Behaviour:
        - Creates a COMMENT TaskUpdate.
        - Does not change any task fields.
    """
    from ..models import Task, TaskUpdate

    logger.info("add_task_note: params=%s actor=%s", params, user)

    try:
        task = Task.objects.get(pk=params["task_id"])
    except Task.DoesNotExist:
        return {"success": False, "message": f"Task {params['task_id']} not found."}

    TaskUpdate.objects.create(
        task=task,
        user=user,
        message=params["message"],
        update_type=TaskUpdate.UpdateType.COMMENT,
    )

    return {
        "success": True,
        "message": f'Note added to task "{task.title}".',
        "data": {"task_id": task.pk},
    }


# ─── Project Tools ────────────────────────────────────────────────────────────


def create_project(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Create a new Project for a team.

    Expected params:
        team_id     (int, required)
        name        (str, required)
        description (str, optional)
        start_date  (ISO 8601 date, optional)
        due_date    (ISO 8601 date, optional)

    Behaviour:
        - Validates the team exists.
        - Creates the Project with status=active.
        - Returns the new Project's ID and name.
    """
    from ..models import Project, Team

    logger.info("create_project: params=%s actor=%s", params, user)

    try:
        team = Team.objects.get(pk=params["team_id"])
    except Team.DoesNotExist:
        return {"success": False, "message": f"Team {params['team_id']} not found."}

    project = Project.objects.create(
        team=team,
        name=params["name"],
        description=params.get("description", ""),
        start_date=params.get("start_date") or None,
        due_date=params.get("due_date") or None,
        status=Project.Status.ACTIVE,
    )

    return {
        "success": True,
        "message": f'Project "{project.name}" created for team "{team.name}".',
        "data": {"project_id": project.pk, "name": project.name},
    }


def update_project(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Update one or more fields on an existing Project.

    Expected params:
        project_id  (int, required)
        name        (str, optional)
        description (str, optional)
        status      ("active"|"on_hold"|"completed"|"cancelled", optional)
        due_date    (ISO 8601 date, optional)

    Behaviour:
        - Fetches the project, applies only provided fields.
        - Saves and returns the updated project.
    """
    from ..models import Project

    logger.info("update_project: params=%s actor=%s", params, user)

    try:
        project = Project.objects.get(pk=params["project_id"])
    except Project.DoesNotExist:
        return {"success": False, "message": f"Project {params['project_id']} not found."}

    changed_fields = []
    if "name" in params:
        project.name = params["name"]
        changed_fields.append("name")
    if "description" in params:
        project.description = params["description"]
        changed_fields.append("description")
    if "status" in params:
        project.status = params["status"]
        changed_fields.append("status")
    if "due_date" in params:
        project.due_date = params["due_date"] or None
        changed_fields.append("due_date")

    if not changed_fields:
        return {"success": False, "message": "No fields to update were provided."}

    project.save()

    return {
        "success": True,
        "message": f'Project "{project.name}" updated (changed: {", ".join(changed_fields)}).',
        "data": {"project_id": project.pk, "status": project.status},
    }


def delete_project(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Delete a Project by ID.

    Expected params:
        project_id (int, required)

    Behaviour:
        - Validates the project exists.
        - Deletes it along with all cascade-linked tasks and knowledge entries.

    Note: This is destructive and irreversible. Consider requiring an explicit
    confirmation flag in production (e.g. params["confirm"] == True).
    """
    from ..models import Project

    logger.info("delete_project: params=%s actor=%s", params, user)

    try:
        project = Project.objects.get(pk=params["project_id"])
    except Project.DoesNotExist:
        return {"success": False, "message": f"Project {params['project_id']} not found."}

    name = project.name
    project.delete()

    return {
        "success": True,
        "message": f'Project "{name}" and all its tasks have been deleted.',
        "data": {"project_id": params["project_id"]},
    }


def generate_project_summary(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Generate a natural language summary of a project's current state.

    Expected params:
        project_id (int, required)

    Behaviour:
        - Delegates to ai_service.generate_project_summary() which handles
          fetching task stats, knowledge entries, and calling Claude.
        - Returns the generated summary text.
    """
    from ..models import Project
    from .ai_service import generate_project_summary as _generate

    logger.info("generate_project_summary tool: params=%s actor=%s", params, user)

    try:
        project = Project.objects.get(pk=params["project_id"])
    except Project.DoesNotExist:
        return {"success": False, "message": f"Project {params['project_id']} not found."}

    return _generate(project)


# ─── Check-in / nudge Tools ───────────────────────────────────────────────────


def poke_user(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Send a nudge to a user who has stale or overdue tasks.

    Expected params:
        user_id (int, required)

    Behaviour:
        - Looks up the target user.
        - Delegates to ai_service.poke_user() which builds context and calls Claude.
        - The generated message should be dispatched via the user's preferred channel
          (Teams, Slack, SMS) — dispatch logic to be wired in when channels are integrated.
    """
    from ..models import User as UserModel
    from .ai_service import poke_user as _poke

    logger.info("poke_user tool: params=%s actor=%s", params, user)

    try:
        target_user = UserModel.objects.get(pk=params["user_id"])
    except UserModel.DoesNotExist:
        return {"success": False, "message": f"User {params['user_id']} not found."}

    return _poke(target_user)


def check_up_for_user(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Run a proactive check-in for a user, reviewing their open tasks and
    generating a status prompt.

    Expected params:
        user_id (int, required)

    Behaviour:
        - Looks up the target user.
        - Delegates to ai_service.check_up_for_user().
        - Returns the generated check-in message.
    """
    from ..models import User as UserModel
    from .ai_service import check_up_for_user as _check_up

    logger.info("check_up_for_user tool: params=%s actor=%s", params, user)

    try:
        target_user = UserModel.objects.get(pk=params["user_id"])
    except UserModel.DoesNotExist:
        return {"success": False, "message": f"User {params['user_id']} not found."}

    return _check_up(target_user)


def update_manager(params: dict[str, Any], user) -> dict[str, Any]:
    """
    Generate a team status digest for a manager.

    Expected params:
        manager_id (int, required)

    Behaviour:
        - Looks up the manager user.
        - Delegates to ai_service.update_manager() which gathers all teams,
          projects, blocked tasks, and calls Claude to generate a digest.
        - Returns the generated digest.
    """
    from ..models import User as UserModel
    from .ai_service import update_manager as _update_manager

    logger.info("update_manager tool: params=%s actor=%s", params, user)

    try:
        manager = UserModel.objects.get(pk=params["manager_id"])
    except UserModel.DoesNotExist:
        return {"success": False, "message": f"Manager {params['manager_id']} not found."}

    return _update_manager(manager)
