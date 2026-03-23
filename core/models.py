from django.contrib.auth.models import AbstractUser
from django.db import models
from pgvector.django import VectorField


class Team(models.Model):
    name = models.CharField(max_length=255)
    managers = models.ManyToManyField(
        "core.User",
        blank=True,
        related_name="managed_teams",
    )

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        DEVELOPER = "developer", "Developer"
        DESIGNER = "designer", "Designer"
        MANAGER = "manager", "Manager"
        QA = "qa", "QA"
        OTHER = "other", "Other"

    # Override first_name/last_name with a single display name field
    name = models.CharField(max_length=255, blank=True)
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OTHER,
    )

    def __str__(self):
        return self.name or self.username


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On Hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="projects")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    assignee = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    due_date = models.DateField(null=True, blank=True)
    created_by_ai = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    next_nudge_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class ConversationThread(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="threads")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Thread {self.id} — {self.user}"


class ConversationMessage(models.Model):
    class Source(models.TextChoices):
        TEAMS = "teams", "Microsoft Teams"
        SLACK = "slack", "Slack"
        WEB = "web", "Web"
        SMS = "sms", "SMS"

    thread = models.ForeignKey(
        ConversationThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messages")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="messages")
    message_text = models.TextField()
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WEB)
    timestamp = models.DateTimeField(auto_now_add=True)
    interpreted = models.BooleanField(default=False)
    # 1536-dimensional embedding for semantic search (OpenAI ada-002 / Anthropic compatible)
    embedding = VectorField(dimensions=1536, null=True, blank=True)

    def __str__(self):
        return f"[{self.source}] {self.user} at {self.timestamp:%Y-%m-%d %H:%M}"


class TaskUpdate(models.Model):
    class UpdateType(models.TextChoices):
        STATUS_CHANGE = "status_change", "Status Change"
        COMMENT = "comment", "Comment"
        ASSIGNMENT = "assignment", "Assignment"
        AI_GENERATED = "ai_generated", "AI Generated"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="updates")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_updates")
    message = models.TextField()
    update_type = models.CharField(max_length=20, choices=UpdateType.choices)
    previous_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.update_type} on '{self.task}' by {self.user}"


class ProjectKnowledge(models.Model):
    """
    Knowledge repository for a project — used for RAG (retrieval-augmented generation).
    Each entry stores a chunk of text with its vector embedding so the AI can
    retrieve relevant context when answering questions about a project.
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="knowledge_entries",
    )
    content = models.TextField()
    source_message = models.ForeignKey(
        ConversationMessage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_entries",
    )
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Knowledge [{self.project}] — {self.content[:60]}..."
