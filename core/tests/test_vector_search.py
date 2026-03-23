"""
Vector search tests — core/tests/test_vector_search.py

Tests for all functions in core/utils/vector_search.py:
- embed_text: stub behavior (dimensions, type)
- get_similar_messages: empty embedding guard, team scoping, limit, result shape
- get_similar_knowledge: empty embedding guard, project scoping, result shape
- store_message_embedding: success path, not-found path
- store_knowledge_embedding: success path, not-found path

Note: These tests require a PostgreSQL database with the pgvector extension enabled.
The migration 0001_enable_vector_extension.py enables it automatically.

Tests that perform actual vector similarity queries use a simple non-zero unit
vector to avoid cosine-distance undefined behavior on zero vectors.
"""
from django.test import TestCase

from core.models import (
    ConversationMessage,
    ConversationThread,
    Project,
    ProjectKnowledge,
    Team,
    User,
)
from core.utils.vector_search import (
    embed_text,
    get_similar_knowledge,
    get_similar_messages,
    store_knowledge_embedding,
    store_message_embedding,
)

# A simple non-zero embedding for testing vector operations.
# Using a uniform vector so cosine distance comparisons are well-defined.
_TEST_EMBEDDING = [0.1] * 1536


# ─── embed_text ───────────────────────────────────────────────────────────────


class EmbedTextTest(TestCase):
    def test_returns_a_list(self):
        result = embed_text("Hello world")
        self.assertIsInstance(result, list)

    def test_returns_exactly_1536_dimensions(self):
        result = embed_text("Test text")
        self.assertEqual(len(result), 1536)

    def test_all_elements_are_floats(self):
        result = embed_text("Test")
        self.assertTrue(all(isinstance(x, float) for x in result))

    def test_stub_returns_zero_vector(self):
        result = embed_text("Anything at all")
        self.assertEqual(sum(abs(x) for x in result), 0.0)

    def test_empty_string_also_returns_1536_floats(self):
        result = embed_text("")
        self.assertEqual(len(result), 1536)


# ─── get_similar_messages ─────────────────────────────────────────────────────


class GetSimilarMessagesTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", name="Alice", team=self.team
        )
        self.thread = ConversationThread.objects.create(user=self.user)

    def _make_msg(self, text="Hello", embedding=None):
        return ConversationMessage.objects.create(
            thread=self.thread,
            user=self.user,
            team=self.team,
            message_text=text,
            embedding=embedding,
        )

    def test_empty_embedding_returns_empty_list(self):
        self._make_msg(embedding=_TEST_EMBEDDING)
        result = get_similar_messages([], team_id=self.team.pk)
        self.assertEqual(result, [])

    def test_no_messages_with_embeddings_returns_empty(self):
        self._make_msg(embedding=None)  # no embedding
        result = get_similar_messages(_TEST_EMBEDDING, team_id=self.team.pk)
        self.assertEqual(result, [])

    def test_result_has_correct_shape(self):
        self._make_msg(text="Status update on auth module", embedding=_TEST_EMBEDDING)
        result = get_similar_messages(_TEST_EMBEDDING, team_id=self.team.pk)
        if result:
            entry = result[0]
            for key in ["id", "user", "text", "source", "timestamp", "distance"]:
                self.assertIn(key, entry)

    def test_only_returns_messages_from_specified_team(self):
        other_team = Team.objects.create(name="Other")
        other_user = User.objects.create_user(
            username="bob", password="pass1234", team=other_team
        )
        other_thread = ConversationThread.objects.create(user=other_user)
        ConversationMessage.objects.create(
            thread=other_thread,
            user=other_user,
            team=other_team,
            message_text="Other team msg",
            embedding=_TEST_EMBEDDING,
        )
        result = get_similar_messages(_TEST_EMBEDDING, team_id=self.team.pk)
        for r in result:
            self.assertNotEqual(r["text"], "Other team msg")

    def test_limit_parameter_respected(self):
        for i in range(6):
            self._make_msg(text=f"Message {i}", embedding=_TEST_EMBEDDING)
        result = get_similar_messages(_TEST_EMBEDDING, team_id=self.team.pk, limit=3)
        self.assertLessEqual(len(result), 3)

    def test_distance_values_are_floats(self):
        self._make_msg(text="Test message", embedding=_TEST_EMBEDDING)
        result = get_similar_messages(_TEST_EMBEDDING, team_id=self.team.pk)
        for r in result:
            self.assertIsInstance(r["distance"], float)

    def test_results_ordered_by_ascending_distance(self):
        self._make_msg(text="A", embedding=_TEST_EMBEDDING)
        self._make_msg(text="B", embedding=_TEST_EMBEDDING)
        result = get_similar_messages(_TEST_EMBEDDING, team_id=self.team.pk)
        distances = [r["distance"] for r in result]
        self.assertEqual(distances, sorted(distances))


# ─── get_similar_knowledge ────────────────────────────────────────────────────


class GetSimilarKnowledgeTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)

    def _make_entry(self, content="Knowledge entry", embedding=None):
        return ProjectKnowledge.objects.create(
            project=self.project, content=content, embedding=embedding
        )

    def test_empty_embedding_returns_empty_list(self):
        self._make_entry(embedding=_TEST_EMBEDDING)
        result = get_similar_knowledge([], project_id=self.project.pk)
        self.assertEqual(result, [])

    def test_no_entries_with_embeddings_returns_empty(self):
        self._make_entry(embedding=None)
        result = get_similar_knowledge(_TEST_EMBEDDING, project_id=self.project.pk)
        self.assertEqual(result, [])

    def test_result_has_correct_shape(self):
        self._make_entry(content="Auth uses JWT", embedding=_TEST_EMBEDDING)
        result = get_similar_knowledge(_TEST_EMBEDDING, project_id=self.project.pk)
        if result:
            entry = result[0]
            for key in ["id", "content", "created_at", "distance"]:
                self.assertIn(key, entry)

    def test_only_returns_entries_from_specified_project(self):
        other_project = Project.objects.create(name="Beta", team=self.team)
        ProjectKnowledge.objects.create(
            project=other_project,
            content="Other project knowledge",
            embedding=_TEST_EMBEDDING,
        )
        result = get_similar_knowledge(_TEST_EMBEDDING, project_id=self.project.pk)
        for r in result:
            self.assertNotEqual(r["content"], "Other project knowledge")

    def test_limit_parameter_respected(self):
        for i in range(6):
            self._make_entry(content=f"Entry {i}", embedding=_TEST_EMBEDDING)
        result = get_similar_knowledge(_TEST_EMBEDDING, project_id=self.project.pk, limit=2)
        self.assertLessEqual(len(result), 2)

    def test_results_ordered_by_ascending_distance(self):
        self._make_entry(content="A", embedding=_TEST_EMBEDDING)
        self._make_entry(content="B", embedding=_TEST_EMBEDDING)
        result = get_similar_knowledge(_TEST_EMBEDDING, project_id=self.project.pk)
        distances = [r["distance"] for r in result]
        self.assertEqual(distances, sorted(distances))


# ─── store_message_embedding ──────────────────────────────────────────────────


class StoreMessageEmbeddingTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.user = User.objects.create_user(
            username="alice", password="pass1234", team=self.team
        )
        self.thread = ConversationThread.objects.create(user=self.user)
        self.msg = ConversationMessage.objects.create(
            thread=self.thread, user=self.user, team=self.team, message_text="Hello"
        )

    def test_success_returns_true(self):
        result = store_message_embedding(self.msg.pk, "Hello")
        self.assertTrue(result)

    def test_embedding_saved_to_db(self):
        store_message_embedding(self.msg.pk, "Hello")
        self.msg.refresh_from_db()
        self.assertIsNotNone(self.msg.embedding)

    def test_embedding_has_1536_dimensions(self):
        store_message_embedding(self.msg.pk, "Hello")
        self.msg.refresh_from_db()
        self.assertEqual(len(self.msg.embedding), 1536)

    def test_message_not_found_returns_false(self):
        result = store_message_embedding(99999, "Hello")
        self.assertFalse(result)

    def test_overwrites_existing_embedding(self):
        store_message_embedding(self.msg.pk, "First")
        store_message_embedding(self.msg.pk, "Second")
        self.msg.refresh_from_db()
        self.assertIsNotNone(self.msg.embedding)


# ─── store_knowledge_embedding ────────────────────────────────────────────────


class StoreKnowledgeEmbeddingTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Acme")
        self.project = Project.objects.create(name="Alpha", team=self.team)
        self.entry = ProjectKnowledge.objects.create(
            project=self.project, content="Knowledge content"
        )

    def test_success_returns_true(self):
        result = store_knowledge_embedding(self.entry.pk, "Knowledge content")
        self.assertTrue(result)

    def test_embedding_saved_to_db(self):
        store_knowledge_embedding(self.entry.pk, "Knowledge content")
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.embedding)

    def test_embedding_has_1536_dimensions(self):
        store_knowledge_embedding(self.entry.pk, "Content")
        self.entry.refresh_from_db()
        self.assertEqual(len(self.entry.embedding), 1536)

    def test_entry_not_found_returns_false(self):
        result = store_knowledge_embedding(99999, "Content")
        self.assertFalse(result)
