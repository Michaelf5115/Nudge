"""
AI service tests — core/tests/test_ai_service.py

Tests for:
- interpret_user_message: entry point, user-not-found path, tool call routing
- build_context: completeness, team-gated fields, done-task exclusion
- call_claude: stub return shape
- handle_tool_call: unknown tool, exception wrapping, all registered tools
- Proactive triggers: check_up_for_user, poke_user, update_manager, generate_project_summary
- TOOL_DEFINITIONS structure

External API calls (Anthropic SDK) are mocked via unittest.mock.
"""
import datetime
from unittest.mock import patch

from django.test import TestCase

from core.models import (
    ConversationMessage,
    ConversationThread,
    Project,
    Task,
    Team,
    User,
)
from core.services.ai_service import (
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    build_context,
    call_claude,
    check_up_for_user,
    generate_project_summary,
    handle_tool_call,
    interpret_user_message,
    poke_user,
    update_manager,
)

_STUB_RESPONSE = {
    "response": "Test response",
    "tool_calls": [],
    "stop_reason": "end_turn",
}


# ─── interpret_user_message ───────────────────────────────────────────────────


class InterpretUserMessageTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", team=self.team
        )

    def test_user_not_found_returns_error(self):
        result = interpret_user_message(user_id=99999, message="Hello")
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("99999", result["error"])

    def test_success_returns_expected_keys(self):
        result = interpret_user_message(user_id=self.user.pk, message="Hello")
        self.assertTrue(result["success"])
        self.assertIn("response", result)
        self.assertIn("actions_taken", result)
        self.assertIsInstance(result["actions_taken"], list)

    def test_tool_calls_are_dispatched_to_handle_tool_call(self):
        mock_response = {
            "response": "Created a task.",
            "tool_calls": [{"name": "create_task", "input": {"project_id": 999, "title": "T"}}],
            "stop_reason": "tool_use",
        }
        with patch("core.services.ai_service.call_claude", return_value=mock_response):
            with patch("core.services.ai_service.handle_tool_call") as mock_handle:
                mock_handle.return_value = {"success": False, "message": "Project 999 not found."}
                result = interpret_user_message(user_id=self.user.pk, message="Make a task")

        mock_handle.assert_called_once_with(
            tool_name="create_task",
            params={"project_id": 999, "title": "T"},
            user=self.user,
        )
        self.assertEqual(len(result["actions_taken"]), 1)
        self.assertEqual(result["actions_taken"][0]["tool"], "create_task")

    def test_response_text_passed_through_from_claude(self):
        mock_response = {**_STUB_RESPONSE, "response": "Specific Claude reply"}
        with patch("core.services.ai_service.call_claude", return_value=mock_response):
            result = interpret_user_message(user_id=self.user.pk, message="Hello")
        self.assertEqual(result["response"], "Specific Claude reply")

    def test_no_tool_calls_means_empty_actions_taken(self):
        with patch("core.services.ai_service.call_claude", return_value=_STUB_RESPONSE):
            result = interpret_user_message(user_id=self.user.pk, message="Hello")
        self.assertEqual(result["actions_taken"], [])

    def test_multiple_tool_calls_all_dispatched(self):
        mock_response = {
            "response": "Done.",
            "tool_calls": [
                {"name": "create_task", "input": {"project_id": 1, "title": "T1"}},
                {"name": "create_task", "input": {"project_id": 1, "title": "T2"}},
            ],
            "stop_reason": "tool_use",
        }
        with patch("core.services.ai_service.call_claude", return_value=mock_response):
            with patch("core.services.ai_service.handle_tool_call", return_value={"success": True, "message": "ok"}):
                result = interpret_user_message(user_id=self.user.pk, message="Create two tasks")
        self.assertEqual(len(result["actions_taken"]), 2)


# ─── build_context ────────────────────────────────────────────────────────────


class BuildContextTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", name="Alice",
            team=self.team, role=User.Role.DEVELOPER,
        )
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_user_profile_in_context(self):
        ctx = build_context(self.user)
        self.assertEqual(ctx["user"]["id"], self.user.pk)
        self.assertEqual(ctx["user"]["name"], "Alice")
        self.assertEqual(ctx["user"]["role"], "developer")
        self.assertEqual(ctx["user"]["team_id"], self.team.pk)
        self.assertEqual(ctx["user"]["team_name"], "Acme")

    def test_user_with_no_name_uses_username(self):
        user = User.objects.create_user(username="noname", password="pass1234", team=self.team)
        ctx = build_context(user)
        self.assertEqual(ctx["user"]["name"], "noname")

    def test_open_tasks_included(self):
        task = Task.objects.create(
            title="Open Task", project=self.project, assignee=self.user
        )
        ctx = build_context(self.user)
        task_ids = [t["id"] for t in ctx["open_tasks"]]
        self.assertIn(task.pk, task_ids)

    def test_done_tasks_excluded_from_open_tasks(self):
        task = Task.objects.create(
            title="Done Task", project=self.project, assignee=self.user, status="done"
        )
        ctx = build_context(self.user)
        task_ids = [t["id"] for t in ctx["open_tasks"]]
        self.assertNotIn(task.pk, task_ids)

    def test_active_projects_for_team(self):
        ctx = build_context(self.user)
        project_ids = [p["id"] for p in ctx["active_projects"]]
        self.assertIn(self.project.pk, project_ids)

    def test_inactive_projects_excluded(self):
        inactive = Project.objects.create(
            name="Done Project", team=self.team, status="completed"
        )
        ctx = build_context(self.user)
        project_ids = [p["id"] for p in ctx["active_projects"]]
        self.assertNotIn(inactive.pk, project_ids)

    def test_user_without_team_has_empty_lists(self):
        no_team_user = User.objects.create_user(username="loner", password="pass1234")
        ctx = build_context(no_team_user)
        self.assertEqual(ctx["active_projects"], [])
        self.assertEqual(ctx["recent_messages"], [])
        self.assertIsNone(ctx["user"]["team_id"])
        self.assertIsNone(ctx["user"]["team_name"])

    def test_recent_messages_in_context(self):
        thread = ConversationThread.objects.create(user=self.user)
        msg = ConversationMessage.objects.create(
            thread=thread, user=self.user, team=self.team, message_text="Status update"
        )
        ctx = build_context(self.user)
        msg_ids = [m["id"] for m in ctx["recent_messages"]]
        self.assertIn(msg.pk, msg_ids)

    def test_similar_messages_placeholder_is_empty_list(self):
        ctx = build_context(self.user)
        self.assertEqual(ctx["similar_messages"], [])

    def test_open_task_includes_expected_fields(self):
        Task.objects.create(title="Task A", project=self.project, assignee=self.user)
        ctx = build_context(self.user)
        if ctx["open_tasks"]:
            task_data = ctx["open_tasks"][0]
            for key in ["id", "title", "status", "priority", "due_date", "project", "project_id"]:
                self.assertIn(key, task_data)


# ─── call_claude ──────────────────────────────────────────────────────────────


class CallClaudeTest(TestCase):
    def test_stub_returns_expected_shape(self):
        result = call_claude(
            system_prompt=SYSTEM_PROMPT,
            context={"user": {"name": "Alice"}},
            message="Hello",
        )
        self.assertIn("response", result)
        self.assertIn("tool_calls", result)
        self.assertIn("stop_reason", result)
        self.assertIsInstance(result["tool_calls"], list)

    def test_stub_has_no_tool_calls(self):
        result = call_claude(SYSTEM_PROMPT, {}, "Do something")
        self.assertEqual(result["tool_calls"], [])

    def test_stub_stop_reason_is_end_turn(self):
        result = call_claude(SYSTEM_PROMPT, {}, "Hello")
        self.assertEqual(result["stop_reason"], "end_turn")

    def test_stub_response_mentions_user_name_from_context(self):
        result = call_claude(
            SYSTEM_PROMPT,
            context={"user": {"name": "TestUser"}},
            message="Hello",
        )
        self.assertIn("TestUser", result["response"])

    def test_stub_response_is_non_empty_string(self):
        result = call_claude(SYSTEM_PROMPT, {}, "Anything")
        self.assertIsInstance(result["response"], str)
        self.assertGreater(len(result["response"]), 0)


# ─── handle_tool_call ─────────────────────────────────────────────────────────


class HandleToolCallTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass1234")

    def test_unknown_tool_returns_failure_with_message(self):
        result = handle_tool_call("nonexistent_tool", {}, self.user)
        self.assertFalse(result["success"])
        self.assertIn("Unknown tool", result["message"])
        self.assertIn("nonexistent_tool", result["message"])

    def test_known_tool_dispatched_successfully(self):
        team = Team.objects.create(name="Acme")
        project = Project.objects.create(name="Alpha", team=team)
        params = {"project_id": project.pk, "title": "Via handle_tool_call"}
        result = handle_tool_call("create_task", params, self.user)
        self.assertTrue(result["success"])

    def test_exception_in_tool_returns_failure_with_error_message(self):
        with patch("core.services.tools.create_task", side_effect=Exception("DB explosion")):
            result = handle_tool_call("create_task", {}, self.user)
        self.assertFalse(result["success"])
        self.assertIn("DB explosion", result["message"])

    def test_all_13_registered_tools_are_routable(self):
        """Verify that no tool name in TOOL_DEFINITIONS is missing from the registry."""
        for tool_def in TOOL_DEFINITIONS:
            result = handle_tool_call(tool_def["name"], {}, self.user)
            # Should NOT return "Unknown tool"
            self.assertNotIn("Unknown tool", result.get("message", ""), msg=tool_def["name"])


# ─── Proactive triggers ───────────────────────────────────────────────────────


class CheckUpForUserTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", team=self.team
        )
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_returns_expected_shape(self):
        result = check_up_for_user(self.user)
        self.assertTrue(result["success"])
        self.assertIn("message", result)
        self.assertIn("data", result)
        self.assertEqual(result["data"]["user_id"], self.user.pk)
        self.assertIn("open_task_count", result["data"])

    def test_open_task_count_is_accurate(self):
        Task.objects.create(title="T1", project=self.project, assignee=self.user)
        Task.objects.create(title="T2", project=self.project, assignee=self.user)
        Task.objects.create(
            title="T3 done", project=self.project, assignee=self.user, status="done"
        )
        result = check_up_for_user(self.user)
        self.assertEqual(result["data"]["open_task_count"], 2)


class PokeUserTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", team=self.team
        )
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_returns_expected_shape(self):
        result = poke_user(self.user)
        self.assertTrue(result["success"])
        self.assertIn("message", result)
        self.assertIn("data", result)
        self.assertEqual(result["data"]["user_id"], self.user.pk)
        self.assertIn("stale_task_count", result["data"])

    def test_detects_stale_tasks_over_3_days(self):
        stale_time = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=5)
        task = Task.objects.create(
            title="Stale Task", project=self.project, assignee=self.user
        )
        # Force last_updated to a stale timestamp bypassing auto_now
        Task.objects.filter(pk=task.pk).update(last_updated=stale_time)
        result = poke_user(self.user)
        self.assertGreater(result["data"]["stale_task_count"], 0)

    def test_done_tasks_not_counted_as_stale(self):
        stale_time = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=5)
        task = Task.objects.create(
            title="Done Stale", project=self.project, assignee=self.user, status="done"
        )
        Task.objects.filter(pk=task.pk).update(last_updated=stale_time)
        result = poke_user(self.user)
        self.assertEqual(result["data"]["stale_task_count"], 0)


class UpdateManagerTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.manager = User.objects.create_user(
            username="mgr", password="pass1234", role="manager"
        )
        self.team.managers.add(self.manager)
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_returns_expected_shape(self):
        result = update_manager(self.manager)
        self.assertTrue(result["success"])
        self.assertIn("message", result)
        self.assertIn("active_project_count", result["data"])
        self.assertIn("blocked_task_count", result["data"])
        self.assertEqual(result["data"]["manager_id"], self.manager.pk)

    def test_active_project_count_accurate(self):
        Project.objects.create(name="Beta", team=self.team)  # active by default
        Project.objects.create(name="Done", team=self.team, status="completed")
        result = update_manager(self.manager)
        # Both alpha + beta = 2 active projects
        self.assertEqual(result["data"]["active_project_count"], 2)

    def test_blocked_task_count_accurate(self):
        task = Task.objects.create(title="Blocker", project=self.project, status="blocked")
        result = update_manager(self.manager)
        self.assertGreater(result["data"]["blocked_task_count"], 0)


class GenerateProjectSummaryTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def test_returns_expected_shape(self):
        result = generate_project_summary(self.project)
        self.assertTrue(result["success"])
        self.assertIn("summary", result)
        self.assertIn("data", result)
        self.assertEqual(result["data"]["project_id"], self.project.pk)
        self.assertIn("task_stats", result["data"])

    def test_task_stats_include_all_statuses(self):
        Task.objects.create(title="T1", project=self.project, status="todo")
        Task.objects.create(title="T2", project=self.project, status="in_progress")
        Task.objects.create(title="T3", project=self.project, status="done")
        result = generate_project_summary(self.project)
        stats = result["data"]["task_stats"]
        for key in ["total", "todo", "in_progress", "blocked", "done"]:
            self.assertIn(key, stats)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["todo"], 1)
        self.assertEqual(stats["in_progress"], 1)
        self.assertEqual(stats["done"], 1)

    def test_project_with_no_tasks(self):
        result = generate_project_summary(self.project)
        self.assertEqual(result["data"]["task_stats"]["total"], 0)


# ─── TOOL_DEFINITIONS structure ───────────────────────────────────────────────


class ToolDefinitionsTest(TestCase):
    def test_is_a_list(self):
        self.assertIsInstance(TOOL_DEFINITIONS, list)

    def test_has_13_tools(self):
        self.assertEqual(len(TOOL_DEFINITIONS), 13)

    def test_all_tools_have_name_description_input_schema(self):
        for tool in TOOL_DEFINITIONS:
            self.assertIn("name", tool, msg=str(tool))
            self.assertIn("description", tool, msg=tool.get("name"))
            self.assertIn("input_schema", tool, msg=tool.get("name"))

    def test_all_input_schemas_are_objects(self):
        for tool in TOOL_DEFINITIONS:
            schema = tool["input_schema"]
            self.assertEqual(schema["type"], "object", msg=tool["name"])
            self.assertIn("properties", schema, msg=tool["name"])

    def test_tool_names_match_registry(self):
        expected_names = {
            "create_task", "update_task", "delete_task", "complete_task",
            "assign_task", "add_task_note", "create_project", "update_project",
            "delete_project", "generate_project_summary", "poke_user",
            "check_up_for_user", "update_manager",
        }
        actual_names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertEqual(actual_names, expected_names)

    def test_system_prompt_is_non_empty_string(self):
        self.assertIsInstance(SYSTEM_PROMPT, str)
        self.assertGreater(len(SYSTEM_PROMPT), 100)
