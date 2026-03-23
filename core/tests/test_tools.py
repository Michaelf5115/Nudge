"""
Tool handler tests — core/tests/test_tools.py

Tests each tool handler function in core/services/tools.py:
- Success cases with correct return shapes
- Error cases (DoesNotExist)
- Edge cases (no fields to update, already done, cascade behavior)
- Audit trail (TaskUpdate) creation
"""
from django.test import TestCase

from core.models import Project, Task, TaskUpdate, Team, User
from core.services import tools


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_env():
    """Create a minimal test environment: team, project, actor user."""
    team = Team.objects.create(name="Acme")
    project = Project.objects.create(name="Alpha", team=team)
    actor = User.objects.create_user(username="actor", password="pass1234")
    return team, project, actor


# ─── create_task ──────────────────────────────────────────────────────────────


class CreateTaskToolTest(TestCase):
    def setUp(self):
        self.team, self.project, self.actor = make_env()

    def test_success_returns_true_and_task_id(self):
        result = tools.create_task(
            {"project_id": self.project.pk, "title": "New Task"}, self.actor
        )
        self.assertTrue(result["success"])
        self.assertIn("task_id", result["data"])
        self.assertIn("title", result["data"])

    def test_task_is_created_in_db(self):
        tools.create_task({"project_id": self.project.pk, "title": "DB Task"}, self.actor)
        self.assertTrue(Task.objects.filter(title="DB Task").exists())

    def test_created_by_ai_is_true(self):
        result = tools.create_task({"project_id": self.project.pk, "title": "AI"}, self.actor)
        task = Task.objects.get(pk=result["data"]["task_id"])
        self.assertTrue(task.created_by_ai)

    def test_creates_ai_generated_task_update(self):
        result = tools.create_task({"project_id": self.project.pk, "title": "AI"}, self.actor)
        task = Task.objects.get(pk=result["data"]["task_id"])
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=task, update_type=TaskUpdate.UpdateType.AI_GENERATED
            ).exists()
        )

    def test_project_not_found_returns_failure(self):
        result = tools.create_task({"project_id": 99999, "title": "Task"}, self.actor)
        self.assertFalse(result["success"])
        self.assertIn("99999", result["message"])

    def test_assignee_not_found_returns_failure(self):
        result = tools.create_task(
            {"project_id": self.project.pk, "title": "Task", "assignee_id": 99999},
            self.actor,
        )
        self.assertFalse(result["success"])

    def test_optional_params_applied(self):
        assignee = User.objects.create_user(username="assignee", password="pass1234")
        result = tools.create_task(
            {
                "project_id": self.project.pk,
                "title": "Full Task",
                "description": "Details",
                "assignee_id": assignee.pk,
                "priority": "high",
                "due_date": "2026-12-31",
            },
            self.actor,
        )
        self.assertTrue(result["success"])
        task = Task.objects.get(pk=result["data"]["task_id"])
        self.assertEqual(task.priority, "high")
        self.assertEqual(task.assignee, assignee)
        self.assertEqual(task.description, "Details")


# ─── update_task ──────────────────────────────────────────────────────────────


class UpdateTaskToolTest(TestCase):
    def setUp(self):
        self.team, self.project, self.actor = make_env()
        self.task = Task.objects.create(title="Fix bug", project=self.project)

    def test_update_title(self):
        result = tools.update_task(
            {"task_id": self.task.pk, "title": "Updated Title"}, self.actor
        )
        self.assertTrue(result["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Updated Title")

    def test_update_status_creates_status_change_update(self):
        tools.update_task({"task_id": self.task.pk, "status": "in_progress"}, self.actor)
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task, update_type=TaskUpdate.UpdateType.STATUS_CHANGE
            ).exists()
        )

    def test_update_status_records_previous_and_new(self):
        tools.update_task({"task_id": self.task.pk, "status": "in_progress"}, self.actor)
        upd = TaskUpdate.objects.get(
            task=self.task, update_type=TaskUpdate.UpdateType.STATUS_CHANGE
        )
        self.assertEqual(upd.previous_status, "todo")
        self.assertEqual(upd.new_status, "in_progress")

    def test_non_status_update_creates_ai_generated_update(self):
        tools.update_task({"task_id": self.task.pk, "title": "New Title"}, self.actor)
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task, update_type=TaskUpdate.UpdateType.AI_GENERATED
            ).exists()
        )

    def test_task_not_found_returns_failure(self):
        result = tools.update_task({"task_id": 99999, "title": "X"}, self.actor)
        self.assertFalse(result["success"])

    def test_no_fields_provided_returns_failure(self):
        result = tools.update_task({"task_id": self.task.pk}, self.actor)
        self.assertFalse(result["success"])
        self.assertIn("no fields", result["message"].lower())

    def test_update_assignee_to_none(self):
        user = User.objects.create_user(username="bob", password="pass1234")
        self.task.assignee = user
        self.task.save()
        result = tools.update_task({"task_id": self.task.pk, "assignee_id": None}, self.actor)
        self.assertTrue(result["success"])
        self.task.refresh_from_db()
        self.assertIsNone(self.task.assignee)

    def test_update_nonexistent_assignee_returns_failure(self):
        result = tools.update_task(
            {"task_id": self.task.pk, "assignee_id": 99999}, self.actor
        )
        self.assertFalse(result["success"])

    def test_update_priority(self):
        result = tools.update_task(
            {"task_id": self.task.pk, "priority": "critical"}, self.actor
        )
        self.assertTrue(result["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, "critical")


# ─── delete_task ──────────────────────────────────────────────────────────────


class DeleteTaskToolTest(TestCase):
    def setUp(self):
        self.team, self.project, self.actor = make_env()
        self.task = Task.objects.create(title="Fix bug", project=self.project)

    def test_delete_task_success(self):
        pk = self.task.pk
        result = tools.delete_task({"task_id": pk}, self.actor)
        self.assertTrue(result["success"])
        self.assertFalse(Task.objects.filter(pk=pk).exists())

    def test_delete_returns_task_title_in_message(self):
        result = tools.delete_task({"task_id": self.task.pk}, self.actor)
        self.assertIn("Fix bug", result["message"])

    def test_task_not_found_returns_failure(self):
        result = tools.delete_task({"task_id": 99999}, self.actor)
        self.assertFalse(result["success"])

    def test_delete_cascades_task_updates(self):
        TaskUpdate.objects.create(
            task=self.task, user=self.actor, message="Note",
            update_type=TaskUpdate.UpdateType.COMMENT
        )
        task_pk = self.task.pk
        tools.delete_task({"task_id": self.task.pk}, self.actor)
        self.assertFalse(TaskUpdate.objects.filter(task_id=task_pk).exists())


# ─── complete_task ────────────────────────────────────────────────────────────


class CompleteTaskToolTest(TestCase):
    def setUp(self):
        self.team, self.project, self.actor = make_env()
        self.task = Task.objects.create(title="Fix bug", project=self.project)

    def test_complete_task_success(self):
        result = tools.complete_task({"task_id": self.task.pk}, self.actor)
        self.assertTrue(result["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)

    def test_complete_creates_status_change_update(self):
        tools.complete_task({"task_id": self.task.pk}, self.actor)
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task,
                update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
                new_status="done",
            ).exists()
        )

    def test_complete_records_previous_status(self):
        self.task.status = "in_progress"
        self.task.save()
        tools.complete_task({"task_id": self.task.pk}, self.actor)
        upd = TaskUpdate.objects.get(
            task=self.task, update_type=TaskUpdate.UpdateType.STATUS_CHANGE
        )
        self.assertEqual(upd.previous_status, "in_progress")

    def test_already_done_returns_success_without_new_update(self):
        self.task.status = Task.Status.DONE
        self.task.save()
        count_before = TaskUpdate.objects.filter(task=self.task).count()
        result = tools.complete_task({"task_id": self.task.pk}, self.actor)
        self.assertTrue(result["success"])
        self.assertEqual(TaskUpdate.objects.filter(task=self.task).count(), count_before)

    def test_task_not_found_returns_failure(self):
        result = tools.complete_task({"task_id": 99999}, self.actor)
        self.assertFalse(result["success"])


# ─── assign_task ──────────────────────────────────────────────────────────────


class AssignTaskToolTest(TestCase):
    def setUp(self):
        self.team, self.project, self.actor = make_env()
        self.assignee = User.objects.create_user(username="assignee", password="pass1234")
        self.task = Task.objects.create(title="Fix bug", project=self.project)

    def test_assign_task_success(self):
        result = tools.assign_task(
            {"task_id": self.task.pk, "assignee_id": self.assignee.pk}, self.actor
        )
        self.assertTrue(result["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee, self.assignee)

    def test_creates_assignment_update(self):
        tools.assign_task(
            {"task_id": self.task.pk, "assignee_id": self.assignee.pk}, self.actor
        )
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task, update_type=TaskUpdate.UpdateType.ASSIGNMENT
            ).exists()
        )

    def test_previous_assignee_in_update_message(self):
        original = User.objects.create_user(username="orig", password="pass1234", name="Original")
        self.task.assignee = original
        self.task.save()
        tools.assign_task(
            {"task_id": self.task.pk, "assignee_id": self.assignee.pk}, self.actor
        )
        upd = TaskUpdate.objects.get(task=self.task, update_type=TaskUpdate.UpdateType.ASSIGNMENT)
        self.assertIn("Original", upd.message)

    def test_task_not_found_returns_failure(self):
        result = tools.assign_task(
            {"task_id": 99999, "assignee_id": self.assignee.pk}, self.actor
        )
        self.assertFalse(result["success"])

    def test_assignee_not_found_returns_failure(self):
        result = tools.assign_task({"task_id": self.task.pk, "assignee_id": 99999}, self.actor)
        self.assertFalse(result["success"])

    def test_data_contains_assignee_id(self):
        result = tools.assign_task(
            {"task_id": self.task.pk, "assignee_id": self.assignee.pk}, self.actor
        )
        self.assertEqual(result["data"]["assignee_id"], self.assignee.pk)


# ─── add_task_note ────────────────────────────────────────────────────────────


class AddTaskNoteToolTest(TestCase):
    def setUp(self):
        self.team, self.project, self.actor = make_env()
        self.task = Task.objects.create(title="Fix bug", project=self.project)

    def test_creates_comment_task_update(self):
        result = tools.add_task_note(
            {"task_id": self.task.pk, "message": "Found the root cause."}, self.actor
        )
        self.assertTrue(result["success"])
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task,
                update_type=TaskUpdate.UpdateType.COMMENT,
                message="Found the root cause.",
            ).exists()
        )

    def test_does_not_change_task_status_or_title(self):
        original_title = self.task.title
        original_status = self.task.status
        tools.add_task_note({"task_id": self.task.pk, "message": "A note"}, self.actor)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, original_title)
        self.assertEqual(self.task.status, original_status)

    def test_task_not_found_returns_failure(self):
        result = tools.add_task_note({"task_id": 99999, "message": "Note"}, self.actor)
        self.assertFalse(result["success"])


# ─── create_project ───────────────────────────────────────────────────────────


class CreateProjectToolTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.actor = User.objects.create_user(username="actor", password="pass1234")

    def test_create_project_success(self):
        result = tools.create_project(
            {"team_id": self.team.pk, "name": "New Project"}, self.actor
        )
        self.assertTrue(result["success"])
        self.assertIn("project_id", result["data"])

    def test_project_created_with_active_status(self):
        result = tools.create_project({"team_id": self.team.pk, "name": "P"}, self.actor)
        project = Project.objects.get(pk=result["data"]["project_id"])
        self.assertEqual(project.status, Project.Status.ACTIVE)

    def test_team_not_found_returns_failure(self):
        result = tools.create_project({"team_id": 99999, "name": "P"}, self.actor)
        self.assertFalse(result["success"])

    def test_with_optional_dates(self):
        result = tools.create_project(
            {
                "team_id": self.team.pk,
                "name": "Dated Project",
                "start_date": "2026-01-01",
                "due_date": "2026-12-31",
                "description": "A project with dates",
            },
            self.actor,
        )
        self.assertTrue(result["success"])
        project = Project.objects.get(pk=result["data"]["project_id"])
        self.assertEqual(str(project.start_date), "2026-01-01")


# ─── update_project ───────────────────────────────────────────────────────────


class UpdateProjectToolTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.actor = User.objects.create_user(username="actor", password="pass1234")

    def test_update_name(self):
        result = tools.update_project(
            {"project_id": self.project.pk, "name": "Beta"}, self.actor
        )
        self.assertTrue(result["success"])
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Beta")

    def test_update_status(self):
        result = tools.update_project(
            {"project_id": self.project.pk, "status": "completed"}, self.actor
        )
        self.assertTrue(result["success"])
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "completed")

    def test_project_not_found_returns_failure(self):
        result = tools.update_project({"project_id": 99999, "name": "X"}, self.actor)
        self.assertFalse(result["success"])

    def test_no_fields_provided_returns_failure(self):
        result = tools.update_project({"project_id": self.project.pk}, self.actor)
        self.assertFalse(result["success"])
        self.assertIn("no fields", result["message"].lower())

    def test_data_contains_project_id_and_status(self):
        result = tools.update_project(
            {"project_id": self.project.pk, "status": "on_hold"}, self.actor
        )
        self.assertEqual(result["data"]["project_id"], self.project.pk)
        self.assertEqual(result["data"]["status"], "on_hold")


# ─── delete_project ───────────────────────────────────────────────────────────


class DeleteProjectToolTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.actor = User.objects.create_user(username="actor", password="pass1234")

    def test_delete_project_success(self):
        pk = self.project.pk
        result = tools.delete_project({"project_id": pk}, self.actor)
        self.assertTrue(result["success"])
        self.assertFalse(Project.objects.filter(pk=pk).exists())

    def test_delete_cascades_tasks(self):
        task = Task.objects.create(title="Task", project=self.project)
        tools.delete_project({"project_id": self.project.pk}, self.actor)
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_project_not_found_returns_failure(self):
        result = tools.delete_project({"project_id": 99999}, self.actor)
        self.assertFalse(result["success"])

    def test_returns_project_name_in_message(self):
        result = tools.delete_project({"project_id": self.project.pk}, self.actor)
        self.assertIn("Alpha", result["message"])


# ─── poke_user, check_up_for_user, update_manager tools ──────────────────────


class CheckInToolsTest(TestCase):
    """
    Tests for delegation tools. The actual logic lives in ai_service.py;
    these tests verify the lookup + delegation contract.
    """

    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.actor = User.objects.create_user(username="actor", password="pass1234")
        self.target = User.objects.create_user(username="target", password="pass1234")

    def test_poke_user_valid_user_returns_success_key(self):
        result = tools.poke_user({"user_id": self.target.pk}, self.actor)
        self.assertIn("success", result)

    def test_poke_user_not_found_returns_failure(self):
        result = tools.poke_user({"user_id": 99999}, self.actor)
        self.assertFalse(result["success"])
        self.assertIn("99999", result["message"])

    def test_check_up_for_user_valid_returns_success_key(self):
        result = tools.check_up_for_user({"user_id": self.target.pk}, self.actor)
        self.assertIn("success", result)

    def test_check_up_for_user_not_found_returns_failure(self):
        result = tools.check_up_for_user({"user_id": 99999}, self.actor)
        self.assertFalse(result["success"])

    def test_update_manager_valid_returns_success_key(self):
        result = tools.update_manager({"manager_id": self.target.pk}, self.actor)
        self.assertIn("success", result)

    def test_update_manager_not_found_returns_failure(self):
        result = tools.update_manager({"manager_id": 99999}, self.actor)
        self.assertFalse(result["success"])
        self.assertIn("99999", result["message"])
