"""
View tests — core/tests/test_views.py

Tests for all API endpoints using DRF's APIClient:
- CRUD operations on all ViewSets
- Custom actions: complete, assign, interpret
- AI endpoint request/response shapes
- Authentication enforcement
- Proper HTTP status codes
"""
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    ConversationMessage,
    ConversationThread,
    Project,
    Task,
    TaskUpdate,
    Team,
    User,
)


# ─── Authentication ───────────────────────────────────────────────────────────


class AuthenticationRequiredTest(APITestCase):
    """All endpoints must reject unauthenticated requests."""

    def test_teams_requires_auth(self):
        response = self.client.get("/api/teams/")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_users_requires_auth(self):
        response = self.client.get("/api/users/")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_projects_requires_auth(self):
        response = self.client.get("/api/projects/")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_tasks_requires_auth(self):
        response = self.client.get("/api/tasks/")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_ai_interpret_requires_auth(self):
        response = self.client.post(
            "/api/ai/interpret/", {"user_id": 1, "message": "Hi"}, format="json"
        )
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ─── TeamViewSet ──────────────────────────────────────────────────────────────


class TeamViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Acme")

    def test_list_teams_returns_200(self):
        response = self.client.get("/api/teams/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_create_team_returns_201(self):
        response = self.client.post("/api/teams/", {"name": "Beta"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Beta")
        self.assertIn("member_count", response.data)

    def test_retrieve_team_returns_200(self):
        response = self.client.get(f"/api/teams/{self.team.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Acme")

    def test_partial_update_team(self):
        response = self.client.patch(
            f"/api/teams/{self.team.pk}/", {"name": "Acme Corp"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Acme Corp")

    def test_delete_team_returns_204(self):
        response = self.client.delete(f"/api/teams/{self.team.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())

    def test_retrieve_nonexistent_team_returns_404(self):
        response = self.client.get("/api/teams/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_search_teams(self):
        Team.objects.create(name="Gamma Corp")
        response = self.client.get("/api/teams/?search=Acme")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [t["name"] for t in response.data["results"]]
        self.assertIn("Acme", names)
        self.assertNotIn("Gamma Corp", names)

    def test_team_response_includes_member_count(self):
        response = self.client.get(f"/api/teams/{self.team.pk}/")
        self.assertIn("member_count", response.data)
        self.assertEqual(response.data["member_count"], 0)


# ─── UserViewSet ──────────────────────────────────────────────────────────────


class UserViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)

    def test_list_users_returns_200(self):
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_user_uses_create_serializer(self):
        data = {"username": "newuser", "password": "securepass123", "role": "developer"}
        response = self.client.post("/api/users/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)

    def test_create_user_without_password_returns_400(self):
        data = {"username": "nopassuser"}
        response = self.client.post("/api/users/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_user_returns_200(self):
        response = self.client.get(f"/api/users/{self.user.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "alice")

    def test_filter_by_role(self):
        User.objects.create_user(username="dev", password="pass1234", role="developer")
        User.objects.create_user(username="mgr", password="pass1234", role="manager")
        response = self.client.get("/api/users/?role=developer")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for u in response.data["results"]:
            self.assertEqual(u["role"], "developer")

    def test_filter_by_is_active(self):
        User.objects.create_user(username="inactive", password="pass1234", is_active=False)
        response = self.client.get("/api/users/?is_active=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for u in response.data["results"]:
            self.assertTrue(u["is_active"])

    def test_list_response_does_not_include_password(self):
        response = self.client.get("/api/users/")
        for u in response.data["results"]:
            self.assertNotIn("password", u)


# ─── ProjectViewSet ───────────────────────────────────────────────────────────


class ProjectViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_list_projects_returns_200(self):
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_project_returns_201(self):
        data = {"name": "Beta", "team": self.team.pk}
        response = self.client.post("/api/projects/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Beta")

    def test_retrieve_project_returns_200(self):
        response = self.client.get(f"/api/projects/{self.project.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Alpha")

    def test_partial_update_project(self):
        response = self.client.patch(
            f"/api/projects/{self.project.pk}/", {"status": "on_hold"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "on_hold")

    def test_delete_project_returns_204(self):
        response = self.client.delete(f"/api/projects/{self.project.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_filter_by_status(self):
        Project.objects.create(name="Completed P", team=self.team, status="completed")
        response = self.client.get("/api/projects/?status=completed")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for p in response.data["results"]:
            self.assertEqual(p["status"], "completed")

    def test_filter_by_team(self):
        other_team = Team.objects.create(name="Other")
        Project.objects.create(name="Other P", team=other_team)
        response = self.client.get(f"/api/projects/?team={self.team.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for p in response.data["results"]:
            self.assertEqual(p["team"], self.team.pk)


# ─── TaskViewSet ──────────────────────────────────────────────────────────────


class TaskViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.task = Task.objects.create(
            title="Fix bug", project=self.project, assignee=self.user
        )

    def test_list_tasks_returns_200(self):
        response = self.client.get("/api/tasks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_task_returns_201(self):
        data = {"title": "New Task", "project": self.project.pk}
        response = self.client.post("/api/tasks/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "New Task")

    def test_retrieve_task_includes_assignee_detail(self):
        response = self.client.get(f"/api/tasks/{self.task.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("assignee_detail", response.data)
        self.assertEqual(response.data["assignee_detail"]["username"], "alice")

    def test_update_task(self):
        response = self.client.patch(
            f"/api/tasks/{self.task.pk}/", {"status": "in_progress"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "in_progress")

    def test_delete_task_returns_204(self):
        response = self.client.delete(f"/api/tasks/{self.task.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_filter_by_project(self):
        other_project = Project.objects.create(name="Beta", team=self.team)
        Task.objects.create(title="Other task", project=other_project)
        response = self.client.get(f"/api/tasks/?project={self.project.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for t in response.data["results"]:
            self.assertEqual(t["project"], self.project.pk)

    def test_filter_by_status(self):
        Task.objects.create(title="Done task", project=self.project, status="done")
        response = self.client.get("/api/tasks/?status=done")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for t in response.data["results"]:
            self.assertEqual(t["status"], "done")

    def test_complete_action_sets_status_done(self):
        response = self.client.post(f"/api/tasks/{self.task.pk}/complete/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "done")

    def test_complete_action_creates_task_update(self):
        self.client.post(f"/api/tasks/{self.task.pk}/complete/")
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task,
                update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
                new_status="done",
            ).exists()
        )

    def test_assign_action_updates_assignee(self):
        bob = User.objects.create_user(username="bob", password="pass1234")
        response = self.client.post(
            f"/api/tasks/{self.task.pk}/assign/",
            {"assignee_id": bob.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assignee"], bob.pk)

    def test_assign_action_creates_task_update(self):
        bob = User.objects.create_user(username="bob", password="pass1234")
        self.client.post(
            f"/api/tasks/{self.task.pk}/assign/",
            {"assignee_id": bob.pk},
            format="json",
        )
        self.assertTrue(
            TaskUpdate.objects.filter(
                task=self.task, update_type=TaskUpdate.UpdateType.ASSIGNMENT
            ).exists()
        )

    def test_assign_without_assignee_id_returns_400(self):
        response = self.client.post(f"/api/tasks/{self.task.pk}/assign/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_invalid_user_returns_404(self):
        response = self.client.post(
            f"/api/tasks/{self.task.pk}/assign/",
            {"assignee_id": 99999},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_created_by_ai(self):
        Task.objects.create(title="AI task", project=self.project, created_by_ai=True)
        response = self.client.get("/api/tasks/?created_by_ai=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for t in response.data["results"]:
            self.assertTrue(t["created_by_ai"])


# ─── ConversationMessageViewSet ───────────────────────────────────────────────


class ConversationMessageViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Acme")
        self.thread = ConversationThread.objects.create(user=self.user)
        self.msg = ConversationMessage.objects.create(
            thread=self.thread, user=self.user, team=self.team, message_text="Hello"
        )

    def test_list_messages_returns_200(self):
        response = self.client.get("/api/conversations/messages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_message_returns_201(self):
        data = {
            "thread": self.thread.pk,
            "user": self.user.pk,
            "team": self.team.pk,
            "message_text": "New message",
        }
        response = self.client.post("/api/conversations/messages/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_list_response_has_no_embedding_field(self):
        response = self.client.get("/api/conversations/messages/")
        for msg in response.data["results"]:
            self.assertNotIn("embedding", msg)

    def test_filter_by_thread(self):
        response = self.client.get(f"/api/conversations/messages/?thread={self.thread.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for msg in response.data["results"]:
            self.assertEqual(msg["thread"], self.thread.pk)

    def test_interpret_already_interpreted_message_returns_200_with_detail(self):
        self.msg.interpreted = True
        self.msg.save()
        response = self.client.post(f"/api/conversations/messages/{self.msg.pk}/interpret/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("detail", response.data)

    def test_interpret_uninterpreted_message_returns_200_with_ai_response(self):
        response = self.client.post(f"/api/conversations/messages/{self.msg.pk}/interpret/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)

    def test_interpret_marks_message_as_interpreted_on_success(self):
        self.client.post(f"/api/conversations/messages/{self.msg.pk}/interpret/")
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.interpreted)


# ─── TaskUpdateViewSet ────────────────────────────────────────────────────────


class TaskUpdateViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.task = Task.objects.create(title="Task", project=self.project)
        TaskUpdate.objects.create(
            task=self.task,
            user=self.user,
            message="Created",
            update_type=TaskUpdate.UpdateType.AI_GENERATED,
        )

    def test_list_updates_returns_200(self):
        response = self.client.get("/api/task-updates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_not_allowed_returns_405(self):
        data = {
            "task": self.task.pk,
            "user": self.user.pk,
            "message": "Test",
            "update_type": "comment",
        }
        response = self.client.post("/api/task-updates/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_filter_by_task(self):
        response = self.client.get(f"/api/task-updates/?task={self.task.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for update in response.data["results"]:
            self.assertEqual(update["task"], self.task.pk)

    def test_filter_by_update_type(self):
        response = self.client.get("/api/task-updates/?update_type=ai_generated")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for update in response.data["results"]:
            self.assertEqual(update["update_type"], "ai_generated")

    def test_response_includes_user_detail(self):
        response = self.client.get("/api/task-updates/")
        for update in response.data["results"]:
            self.assertIn("user_detail", update)


# ─── AIInterpretView ──────────────────────────────────────────────────────────


class AIInterpretViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)

    def test_valid_request_returns_200(self):
        data = {"user_id": self.user.pk, "message": "What are my tasks?"}
        response = self.client.post("/api/ai/interpret/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)
        self.assertIn("response", response.data)
        self.assertIn("actions_taken", response.data)

    def test_missing_user_id_returns_400(self):
        response = self.client.post("/api/ai/interpret/", {"message": "Hello"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)

    def test_missing_message_returns_400(self):
        response = self.client.post(
            "/api/ai/interpret/", {"user_id": self.user.pk}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message", response.data)

    def test_nonexistent_user_id_returns_200_with_error(self):
        # AI service handles missing user gracefully with error dict
        data = {"user_id": 99999, "message": "Hello"}
        response = self.client.post("/api/ai/interpret/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data.get("success"))
        self.assertIn("error", response.data)

    def test_empty_body_returns_400(self):
        response = self.client.post("/api/ai/interpret/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─── AI Proactive Views ───────────────────────────────────────────────────────


class AIProactiveViewsTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")
        self.client.force_authenticate(user=self.user)
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_check_in_valid_user_returns_200(self):
        response = self.client.post(f"/api/ai/check-in/{self.user.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)
        self.assertIn("message", response.data)

    def test_check_in_invalid_user_returns_404(self):
        response = self.client.post("/api/ai/check-in/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_poke_valid_user_returns_200(self):
        response = self.client.post(f"/api/ai/poke/{self.user.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)

    def test_poke_invalid_user_returns_404(self):
        response = self.client.post("/api/ai/poke/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_update_valid_user_returns_200(self):
        response = self.client.post(f"/api/ai/manager-update/{self.user.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)

    def test_manager_update_invalid_user_returns_404(self):
        response = self.client.post("/api/ai/manager-update/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_project_summary_valid_project_returns_200(self):
        response = self.client.post(f"/api/ai/project-summary/{self.project.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("success", response.data)

    def test_project_summary_invalid_project_returns_404(self):
        response = self.client.post("/api/ai/project-summary/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
