"""
Serializer tests — core/tests/test_serializers.py

Tests for field validation, required fields, read-only enforcement,
nested serializers, write-only fields, and password handling.
"""
from django.test import TestCase

from core.models import (
    ConversationMessage,
    ConversationThread,
    Project,
    Task,
    TaskUpdate,
    Team,
    User,
)
from core.serializers import (
    AIActionResponseSerializer,
    ConversationMessageCreateSerializer,
    ConversationMessageSerializer,
    InterpretRequestSerializer,
    InterpretResponseSerializer,
    ProjectSerializer,
    TaskSerializer,
    TaskUpdateSerializer,
    TeamSerializer,
    UserCreateSerializer,
    UserSerializer,
)


# ─── UserSerializer ───────────────────────────────────────────────────────────


class UserSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice",
            password="pass1234",
            name="Alice Smith",
            email="alice@example.com",
            team=self.team,
            role=User.Role.DEVELOPER,
        )

    def test_contains_expected_fields(self):
        s = UserSerializer(self.user)
        for field in ["id", "username", "email", "name", "team", "role", "is_active", "date_joined"]:
            self.assertIn(field, s.data)

    def test_password_not_in_output(self):
        s = UserSerializer(self.user)
        self.assertNotIn("password", s.data)

    def test_date_joined_is_read_only(self):
        data = {"date_joined": "2020-01-01T00:00:00Z", "username": "x", "role": "other"}
        s = UserSerializer(self.user, data=data, partial=True)
        self.assertTrue(s.is_valid())
        self.assertNotIn("date_joined", s.validated_data)

    def test_team_is_pk(self):
        s = UserSerializer(self.user)
        self.assertEqual(s.data["team"], self.team.pk)


# ─── UserCreateSerializer ─────────────────────────────────────────────────────


class UserCreateSerializerTest(TestCase):
    def test_creates_user_with_hashed_password(self):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "name": "New User",
            "role": "developer",
            "password": "securepassword123",
        }
        s = UserCreateSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertNotEqual(user.password, "securepassword123")
        self.assertTrue(user.check_password("securepassword123"))

    def test_password_is_write_only_not_in_output(self):
        data = {"username": "u2", "password": "pass1234"}
        s = UserCreateSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        out = UserCreateSerializer(user)
        self.assertNotIn("password", out.data)

    def test_password_min_length_enforced(self):
        data = {"username": "u3", "password": "short"}
        s = UserCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("password", s.errors)

    def test_username_required(self):
        data = {"password": "pass1234"}
        s = UserCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("username", s.errors)

    def test_password_required(self):
        data = {"username": "u4"}
        s = UserCreateSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("password", s.errors)


# ─── TeamSerializer ───────────────────────────────────────────────────────────


class TeamSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.mgr = User.objects.create_user(username="mgr", password="pass1234")
        self.member = User.objects.create_user(
            username="member", password="pass1234", team=self.team
        )

    def test_member_count_is_correct(self):
        s = TeamSerializer(self.team)
        self.assertEqual(s.data["member_count"], 1)

    def test_managers_nested_read_only(self):
        self.team.managers.add(self.mgr)
        s = TeamSerializer(self.team)
        self.assertEqual(len(s.data["managers"]), 1)
        self.assertEqual(s.data["managers"][0]["username"], "mgr")

    def test_manager_ids_write_only_not_in_output(self):
        self.team.managers.add(self.mgr)
        s = TeamSerializer(self.team)
        self.assertNotIn("manager_ids", s.data)

    def test_create_team_with_manager_ids(self):
        mgr2 = User.objects.create_user(username="mgr2", password="pass1234")
        data = {"name": "Beta Team", "manager_ids": [mgr2.pk]}
        s = TeamSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        team = s.save()
        self.assertIn(mgr2, team.managers.all())


# ─── ProjectSerializer ────────────────────────────────────────────────────────


class ProjectSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")

    def test_valid_project_data(self):
        data = {"name": "Project X", "team": self.team.pk}
        s = ProjectSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_name_required(self):
        data = {"team": self.team.pk}
        s = ProjectSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("name", s.errors)

    def test_team_required(self):
        data = {"name": "Project X"}
        s = ProjectSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("team", s.errors)


# ─── TaskSerializer ───────────────────────────────────────────────────────────


class TaskSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.user = User.objects.create_user(
            username="alice", password="pass1234", name="Alice"
        )
        self.task = Task.objects.create(
            title="Fix bug", project=self.project, assignee=self.user
        )

    def test_assignee_detail_nested_in_output(self):
        s = TaskSerializer(self.task)
        self.assertIn("assignee_detail", s.data)
        self.assertEqual(s.data["assignee_detail"]["username"], "alice")

    def test_assignee_id_writable(self):
        s = TaskSerializer(self.task)
        self.assertIn("assignee", s.data)
        self.assertEqual(s.data["assignee"], self.user.pk)

    def test_last_updated_is_read_only(self):
        data = {
            "title": "Updated",
            "project": self.project.pk,
            "last_updated": "2020-01-01T00:00:00Z",
        }
        s = TaskSerializer(self.task, data=data, partial=True)
        self.assertTrue(s.is_valid())
        self.assertNotIn("last_updated", s.validated_data)

    def test_all_expected_fields_present(self):
        s = TaskSerializer(self.task)
        expected = [
            "id", "title", "description", "project", "assignee", "assignee_detail",
            "status", "priority", "due_date", "created_by_ai", "last_updated",
            "next_nudge_date",
        ]
        for field in expected:
            self.assertIn(field, s.data)


# ─── ConversationMessageSerializer ───────────────────────────────────────────


class ConversationMessageSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", team=self.team
        )
        self.thread = ConversationThread.objects.create(user=self.user)
        self.msg = ConversationMessage.objects.create(
            thread=self.thread, user=self.user, team=self.team, message_text="Hello"
        )

    def test_no_embedding_in_output(self):
        s = ConversationMessageSerializer(self.msg)
        self.assertNotIn("embedding", s.data)

    def test_timestamp_is_read_only(self):
        data = {
            "thread": self.thread.pk,
            "user": self.user.pk,
            "team": self.team.pk,
            "message_text": "Hello",
        }
        s = ConversationMessageSerializer(self.msg, data=data, partial=True)
        self.assertTrue(s.is_valid())
        self.assertNotIn("timestamp", s.validated_data)

    def test_interpreted_is_read_only(self):
        data = {
            "thread": self.thread.pk,
            "user": self.user.pk,
            "team": self.team.pk,
            "message_text": "Hello",
            "interpreted": True,
        }
        s = ConversationMessageSerializer(self.msg, data=data, partial=True)
        self.assertTrue(s.is_valid())
        self.assertNotIn("interpreted", s.validated_data)

    def test_create_serializer_has_no_embedding_field(self):
        data = {
            "thread": self.thread.pk,
            "user": self.user.pk,
            "team": self.team.pk,
            "message_text": "New message",
        }
        s = ConversationMessageCreateSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertNotIn("embedding", s.fields)


# ─── TaskUpdateSerializer ─────────────────────────────────────────────────────


class TaskUpdateSerializerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(username="alice", password="pass1234", name="Alice")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.task = Task.objects.create(title="Fix bug", project=self.project)
        self.update = TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="Status changed",
            update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
            previous_status="todo",
            new_status="done",
        )

    def test_user_detail_nested_in_output(self):
        s = TaskUpdateSerializer(self.update)
        self.assertIn("user_detail", s.data)
        self.assertEqual(s.data["user_detail"]["username"], "alice")

    def test_timestamp_read_only(self):
        s = TaskUpdateSerializer(self.update)
        self.assertIn("timestamp", s.data)

    def test_previous_and_new_status_in_output(self):
        s = TaskUpdateSerializer(self.update)
        self.assertEqual(s.data["previous_status"], "todo")
        self.assertEqual(s.data["new_status"], "done")


# ─── AI Request/Response Serializers ─────────────────────────────────────────


class InterpretRequestSerializerTest(TestCase):
    def test_valid_data(self):
        s = InterpretRequestSerializer(data={"user_id": 1, "message": "Hello"})
        self.assertTrue(s.is_valid())

    def test_user_id_required(self):
        s = InterpretRequestSerializer(data={"message": "Hello"})
        self.assertFalse(s.is_valid())
        self.assertIn("user_id", s.errors)

    def test_message_required(self):
        s = InterpretRequestSerializer(data={"user_id": 1})
        self.assertFalse(s.is_valid())
        self.assertIn("message", s.errors)

    def test_user_id_must_be_integer(self):
        s = InterpretRequestSerializer(data={"user_id": "not-an-int", "message": "Hello"})
        self.assertFalse(s.is_valid())
        self.assertIn("user_id", s.errors)


class AIActionResponseSerializerTest(TestCase):
    def test_valid_success_response(self):
        s = AIActionResponseSerializer(data={"success": True, "message": "Done", "data": {}})
        self.assertTrue(s.is_valid())

    def test_data_field_optional(self):
        s = AIActionResponseSerializer(data={"success": True, "message": "Done"})
        self.assertTrue(s.is_valid())

    def test_success_required(self):
        s = AIActionResponseSerializer(data={"message": "Done"})
        self.assertFalse(s.is_valid())
        self.assertIn("success", s.errors)


class InterpretResponseSerializerTest(TestCase):
    def test_valid_response_with_actions(self):
        s = InterpretResponseSerializer(data={
            "success": True,
            "response": "Created a task for you.",
            "actions_taken": [{"tool": "create_task", "result": {"success": True}}],
        })
        self.assertTrue(s.is_valid())

    def test_actions_taken_optional(self):
        s = InterpretResponseSerializer(data={"success": True, "response": "Done"})
        self.assertTrue(s.is_valid())

    def test_error_field_optional(self):
        s = InterpretResponseSerializer(data={
            "success": False,
            "response": "",
            "error": "User not found",
        })
        self.assertTrue(s.is_valid())
