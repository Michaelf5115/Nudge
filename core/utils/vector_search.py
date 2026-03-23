"""
Vector Search Utilities — core/utils/vector_search.py

Provides helper functions for semantic similarity search using pgvector.
All queries use cosine distance (<=> operator in pgvector) which works well
for normalised text embeddings (e.g. OpenAI ada-002, Anthropic Voyage).

To use these utilities you must:
  1. Have the `vector` Postgres extension enabled (migration 0001).
  2. Have pgvector Python package installed.
  3. Populate the `embedding` fields on ConversationMessage / ProjectKnowledge
     before querying (use embed_text() or equivalent in your ingestion pipeline).
"""

from __future__ import annotations

import logging
from typing import Any

from pgvector.django import CosineDistance

logger = logging.getLogger(__name__)


def get_similar_messages(
    query_embedding: list[float],
    team_id: int,
    limit: int = 5,
    max_distance: float = 0.3,
) -> list[dict[str, Any]]:
    """
    Find ConversationMessages in a team whose embeddings are semantically
    closest to the given query_embedding using cosine distance.

    Args:
        query_embedding: A 1536-dimensional float list representing the
                         embedded query text. Must be normalised to unit length
                         for cosine distance to behave correctly.
        team_id:         Only search messages belonging to this team.
        limit:           Maximum number of results to return.
        max_distance:    Cosine distance threshold — results with distance
                         greater than this value are excluded. Range [0, 2];
                         0 = identical, 2 = opposite. Typical useful range: <0.4.

    Returns:
        List of dicts, each containing:
            {
                "id":         int,
                "user":       str,
                "text":       str,
                "source":     str,
                "timestamp":  str (ISO 8601),
                "distance":   float,
            }
        Ordered by ascending cosine distance (most similar first).

    Usage:
        from core.utils.vector_search import get_similar_messages
        embedding = embed_text("What's the status of the auth module?")
        results = get_similar_messages(embedding, team_id=3, limit=5)
    """
    from ..models import ConversationMessage

    if not query_embedding:
        logger.warning("get_similar_messages: empty query_embedding provided")
        return []

    messages = (
        ConversationMessage.objects.filter(
            team_id=team_id,
            embedding__isnull=False,
        )
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .filter(distance__lte=max_distance)
        .select_related("user")
        .order_by("distance")[:limit]
    )

    return [
        {
            "id": m.pk,
            "user": m.user.name or m.user.username,
            "text": m.message_text,
            "source": m.source,
            "timestamp": m.timestamp.isoformat(),
            "distance": round(float(m.distance), 4),
        }
        for m in messages
    ]


def get_similar_knowledge(
    query_embedding: list[float],
    project_id: int,
    limit: int = 5,
    max_distance: float = 0.3,
) -> list[dict[str, Any]]:
    """
    Find ProjectKnowledge entries for a project whose embeddings are
    semantically closest to query_embedding (cosine distance).

    Used for RAG: retrieve relevant knowledge snippets to inject into the
    Claude context when answering questions about a specific project.

    Args:
        query_embedding: 1536-dimensional float list.
        project_id:      Only search knowledge entries for this project.
        limit:           Maximum number of results to return.
        max_distance:    Cosine distance cutoff.

    Returns:
        List of dicts:
            {
                "id":         int,
                "content":    str,
                "created_at": str (ISO 8601),
                "distance":   float,
            }
        Ordered by ascending cosine distance (most relevant first).
    """
    from ..models import ProjectKnowledge

    if not query_embedding:
        logger.warning("get_similar_knowledge: empty query_embedding provided")
        return []

    entries = (
        ProjectKnowledge.objects.filter(
            project_id=project_id,
            embedding__isnull=False,
        )
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .filter(distance__lte=max_distance)
        .order_by("distance")[:limit]
    )

    return [
        {
            "id": e.pk,
            "content": e.content,
            "created_at": e.created_at.isoformat(),
            "distance": round(float(e.distance), 4),
        }
        for e in entries
    ]


def embed_text(text: str) -> list[float]:
    """
    Generate a 1536-dimensional embedding for the given text.

    This is a placeholder. In production, replace with a real embedding call:

    Option A — Anthropic Voyage (recommended with Claude):
        import anthropic
        client = anthropic.Anthropic()
        response = client.embeddings.create(
            model="voyage-2",
            input=[text],
        )
        return response.embeddings[0].embedding

    Option B — OpenAI ada-002 (compatible, widely used):
        import openai
        response = openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )
        return response.data[0].embedding

    Args:
        text: The text to embed. Should be cleaned/truncated to fit within
              the model's token limit before calling.

    Returns:
        A list of 1536 floats.
    """
    logger.warning("embed_text: using stub — returns zero vector. Wire up a real embedding model.")
    # Stub: returns a zero vector of the correct dimensionality
    return [0.0] * 1536


def store_message_embedding(message_id: int, text: str) -> bool:
    """
    Embed text and save the result to ConversationMessage.embedding.

    Call this in a Celery task after a new ConversationMessage is saved to
    avoid blocking the HTTP request cycle.

    Args:
        message_id: PK of the ConversationMessage to update.
        text:       The message_text to embed (pass explicitly to allow
                    pre-processing / truncation before embedding).

    Returns:
        True on success, False on failure.
    """
    from ..models import ConversationMessage

    try:
        message = ConversationMessage.objects.get(pk=message_id)
        embedding = embed_text(text)
        message.embedding = embedding
        message.save(update_fields=["embedding"])
        return True
    except ConversationMessage.DoesNotExist:
        logger.error("store_message_embedding: ConversationMessage %s not found", message_id)
        return False
    except Exception as exc:
        logger.exception("store_message_embedding: failed for message %s: %s", message_id, exc)
        return False


def store_knowledge_embedding(knowledge_id: int, text: str) -> bool:
    """
    Embed text and save the result to ProjectKnowledge.embedding.

    Args:
        knowledge_id: PK of the ProjectKnowledge entry to update.
        text:         The content to embed.

    Returns:
        True on success, False on failure.
    """
    from ..models import ProjectKnowledge

    try:
        entry = ProjectKnowledge.objects.get(pk=knowledge_id)
        embedding = embed_text(text)
        entry.embedding = embedding
        entry.save(update_fields=["embedding"])
        return True
    except ProjectKnowledge.DoesNotExist:
        logger.error("store_knowledge_embedding: ProjectKnowledge %s not found", knowledge_id)
        return False
    except Exception as exc:
        logger.exception("store_knowledge_embedding: failed for entry %s: %s", knowledge_id, exc)
        return False
