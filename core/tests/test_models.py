"""
Model tests — core/tests/test_models.py

Tests for all 8 models: field defaults, __str__ representations,
relationship cascades, choice field validation, and nullable fields.
"""
from django.test import TestCase

from core.models import (
    ConversationMessage,
    ConversationThread,
    Project,
    ProjectKnowledge,
    Task,
    TaskUpdate,
    Team,
    User,
)


# ─── Team ────────────────────────────────────────────────────────────────────


class TeamModelTest(TestCase):
    def test_str(self):
        team = Team.objects.create(name="Acme Team")
        self.assertEqual(str(team), "Acme Team")

    def test_member_count_via_related(self):
        team = Team.objects.create(name="Acme")
        User.objects.create_user(username="u1", password="pass1234", team=team)
        User.objects.create_user(username="u2", password="pass1234", team=team)
        self.assertEqual(team.members.count(), 2)

    def test_team_with_no_members(self):
        team = Team.objects.create(name="Empty")
        self.assertEqual(team.members.count(), 0)

    def test_managers_m2m_relationship(self):
        team = Team.objects.create(name="Acme")
        mgr = User.objects.create_user(username="mgr", password="pass1234")
        team.managers.add(mgr)
        self.assertIn(mgr, team.managers.all())
        self.assertIn(team, mgr.managed_teams.all())


# ─── User ─────────────────────────────────────────────────────────────────────


class UserModelTest(TestCase):
    def test_str_returns_name_when_set(self):
        user = User.objects.create_user(username="alice", password="pass1234", name="Alice Smith")
        self.assertEqual(str(user), "Alice Smith")

    def test_str_falls_back_to_username(self):
        user = User.objects.create_user(username="bob", password="pass1234")
        self.assertEqual(str(user), "bob")

    def test_default_role_is_other(self):
        user = User.objects.create_user(username="charlie", password="pass1234")
        self.assertEqual(user.role, User.Role.OTHER)

    def test_team_nullable_by_default(self):
        user = User.objects.create_user(username="dave", password="pass1234")
        self.assertIsNone(user.team)

    def test_all_role_choices_valid(self):
        for role, _ in User.Role.choices:
            user = User.objects.create_user(username=f"u_{role}", password="pass1234", role=role)
            self.assertEqual(user.role, role)

    def test_team_set_null_on_team_delete(self):
        team = Team.objects.create(name="Acme")
        user = User.objects.create_user(username="alice", password="pass1234", team=team)
        team.delete()
        user.refresh_from_db()
        self.assertIsNone(user.team)


# ─── Project ──────────────────────────────────────────────────────────────────


class ProjectModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")

    def test_str(self):
        project = Project.objects.create(name="Website Redesign", team=self.team)
        self.assertEqual(str(project), "Website Redesign")

    def test_default_status_is_active(self):
        project = Project.objects.create(name="Alpha", team=self.team)
        self.assertEqual(project.status, Project.Status.ACTIVE)

    def test_all_status_choices_valid(self):
        for status, _ in Project.Status.choices:
            p = Project.objects.create(name=f"P-{status}", team=self.team, status=status)
            self.assertEqual(p.status, status)

    def test_optional_dates_nullable(self):
        project = Project.objects.create(name="No Dates", team=self.team)
        self.assertIsNone(project.start_date)
        self.assertIsNone(project.due_date)

    def test_cascade_delete_on_team_delete(self):
        project = Project.objects.create(name="P", team=self.team)
        pk = project.pk
        self.team.delete()
        self.assertFalse(Project.objects.filter(pk=pk).exists())

    def test_description_blank_by_default(self):
        project = Project.objects.create(name="Alpha", team=self.team)
        self.assertEqual(project.description, "")


# ─── Task ─────────────────────────────────────────────────────────────────────


class TaskModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.user = User.objects.create_user(username="alice", password="pass1234")

    def test_str(self):
        task = Task.objects.create(title="Fix login bug", project=self.project)
        self.assertEqual(str(task), "Fix login bug")

    def test_default_status_is_todo(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertEqual(task.status, Task.Status.TODO)

    def test_default_priority_is_medium(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertEqual(task.priority, Task.Priority.MEDIUM)

    def test_created_by_ai_defaults_false(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertFalse(task.created_by_ai)

    def test_assignee_nullable(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertIsNone(task.assignee)

    def test_assignee_set_null_on_user_delete(self):
        task = Task.objects.create(title="Task", project=self.project, assignee=self.user)
        self.user.delete()
        task.refresh_from_db()
        self.assertIsNone(task.assignee)

    def test_last_updated_auto_set_on_create(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertIsNotNone(task.last_updated)

    def test_last_updated_auto_updates_on_save(self):
        task = Task.objects.create(title="Task", project=self.project)
        original = task.last_updated
        task.title = "Updated"
        task.save()
        task.refresh_from_db()
        self.assertGreaterEqual(task.last_updated, original)

    def test_cascade_delete_on_project_delete(self):
        task = Task.objects.create(title="Task", project=self.project)
        pk = task.pk
        self.project.delete()
        self.assertFalse(Task.objects.filter(pk=pk).exists())

    def test_all_status_choices_valid(self):
        for status, _ in Task.Status.choices:
            t = Task.objects.create(title=f"T-{status}", project=self.project, status=status)
            self.assertEqual(t.status, status)

    def test_all_priority_choices_valid(self):
        for priority, _ in Task.Priority.choices:
            t = Task.objects.create(
                title=f"T-{priority}", project=self.project, priority=priority
            )
            self.assertEqual(t.priority, priority)

    def test_next_nudge_date_nullable(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertIsNone(task.next_nudge_date)

    def test_due_date_nullable(self):
        task = Task.objects.create(title="Task", project=self.project)
        self.assertIsNone(task.due_date)


# ─── ConversationThread ───────────────────────────────────────────────────────


class ConversationThreadModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234", name="Alice")

    def test_str_contains_thread_and_user(self):
        thread = ConversationThread.objects.create(user=self.user)
        result = str(thread)
        self.assertIn("Thread", result)
        self.assertIn("Alice", result)

    def test_created_at_auto_set(self):
        thread = ConversationThread.objects.create(user=self.user)
        self.assertIsNotNone(thread.created_at)

    def test_cascade_delete_on_user_delete(self):
        thread = ConversationThread.objects.create(user=self.user)
        pk = thread.pk
        self.user.delete()
        self.assertFalse(ConversationThread.objects.filter(pk=pk).exists())


# ─── ConversationMessage ──────────────────────────────────────────────────────


class ConversationMessageModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", name="Alice", team=self.team
        )
        self.thread = ConversationThread.objects.create(user=self.user)

    def _make_msg(self, **kwargs):
        defaults = dict(
            thread=self.thread, user=self.user, team=self.team, message_text="Hello"
        )
        defaults.update(kwargs)
        return ConversationMessage.objects.create(**defaults)

    def test_str_contains_source_and_user(self):
        msg = self._make_msg()
        result = str(msg)
        self.assertIn("[web]", result)
        self.assertIn("Alice", result)

    def test_default_source_is_web(self):
        msg = self._make_msg()
        self.assertEqual(msg.source, ConversationMessage.Source.WEB)

    def test_interpreted_defaults_false(self):
        msg = self._make_msg()
        self.assertFalse(msg.interpreted)

    def test_embedding_nullable(self):
        msg = self._make_msg()
        self.assertIsNone(msg.embedding)

    def test_timestamp_auto_set(self):
        msg = self._make_msg()
        self.assertIsNotNone(msg.timestamp)

    def test_all_source_choices_valid(self):
        for source, _ in ConversationMessage.Source.choices:
            msg = self._make_msg(source=source)
            self.assertEqual(msg.source, source)

    def test_cascade_delete_on_thread_delete(self):
        msg = self._make_msg()
        pk = msg.pk
        self.thread.delete()
        self.assertFalse(ConversationMessage.objects.filter(pk=pk).exists())


# ─── TaskUpdate ───────────────────────────────────────────────────────────────


class TaskUpdateModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(username="alice", password="pass1234", name="Alice")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.task = Task.objects.create(title="Fix bug", project=self.project)

    def test_str_contains_update_type_and_task(self):
        update = TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="Status changed",
            update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
        )
        result = str(update)
        self.assertIn("status_change", result)
        self.assertIn("Fix bug", result)

    def test_status_fields_nullable(self):
        update = TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="A comment",
            update_type=TaskUpdate.UpdateType.COMMENT,
        )
        self.assertIsNone(update.previous_status)
        self.assertIsNone(update.new_status)

    def test_timestamp_auto_set(self):
        update = TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="msg",
            update_type=TaskUpdate.UpdateType.COMMENT,
        )
        self.assertIsNotNone(update.timestamp)

    def test_all_update_type_choices_valid(self):
        for update_type, _ in TaskUpdate.UpdateType.choices:
            u = TaskUpdate.objects.create(
                task=self.task,
                user=self.user,
                message="msg",
                update_type=update_type,
            )
            self.assertEqual(u.update_type, update_type)

    def test_cascade_delete_on_task_delete(self):
        update = TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="msg",
            update_type=TaskUpdate.UpdateType.COMMENT,
        )
        pk = update.pk
        self.task.delete()
        self.assertFalse(TaskUpdate.objects.filter(pk=pk).exists())

    def test_with_previous_and_new_status(self):
        update = TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="Changed status",
            update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
            previous_status="todo",
            new_status="in_progress",
        )
        self.assertEqual(update.previous_status, "todo")
        self.assertEqual(update.new_status, "in_progress")


# ─── ProjectKnowledge ─────────────────────────────────────────────────────────


class ProjectKnowledgeModelTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_str_contains_project_name(self):
        entry = ProjectKnowledge.objects.create(
            project=self.project,
            content="Authentication uses JWT tokens.",
        )
        self.assertIn("Alpha", str(entry))

    def test_str_contains_content_preview(self):
        entry = ProjectKnowledge.objects.create(
            project=self.project,
            content="Authentication uses JWT tokens for session management.",
        )
        self.assertIn("Authentication", str(entry))

    def test_str_truncates_long_content(self):
        # __str__ uses content[:60], so output should be bounded
        entry = ProjectKnowledge.objects.create(
            project=self.project, content="A" * 200
        )
        # The truncated part should be at most 60 chars + "..."
        content_part = str(entry).split("—")[-1].strip()
        self.assertLessEqual(len(content_part), 65)

    def test_embedding_nullable(self):
        entry = ProjectKnowledge.objects.create(project=self.project, content="Content")
        self.assertIsNone(entry.embedding)

    def test_source_message_nullable(self):
        entry = ProjectKnowledge.objects.create(project=self.project, content="Content")
        self.assertIsNone(entry.source_message)

    def test_created_at_auto_set(self):
        entry = ProjectKnowledge.objects.create(project=self.project, content="Content")
        self.assertIsNotNone(entry.created_at)

    def test_cascade_delete_on_project_delete(self):
        entry = ProjectKnowledge.objects.create(project=self.project, content="Content")
        pk = entry.pk
        self.project.delete()
        self.assertFalse(ProjectKnowledge.objects.filter(pk=pk).exists())
