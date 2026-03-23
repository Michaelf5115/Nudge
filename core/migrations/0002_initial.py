"""
Migration 0002 — Create all core models.

Depends on 0001 (pgvector extension) and Django's auth migrations
(for AbstractUser's groups / user_permissions M2M tables).

Creation order handles the User <-> Team circular FK:
  1. Team (without managers M2M)
  2. User (with FK → Team)
  3. Project, Task, ConversationThread, ConversationMessage, TaskUpdate, ProjectKnowledge
  4. AddField Team.managers (M2M → User, now that User table exists)
  5. AddField User.groups / user_permissions (standard auth M2M)
"""

import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
import pgvector.django
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0001_enable_vector_extension"),
    ]

    operations = [
        # ── 1. Team (no managers yet — User doesn't exist) ────────────────────
        migrations.CreateModel(
            name="Team",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
            ],
        ),
        # ── 2. User (AbstractUser fields + custom fields) ─────────────────────
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={
                            "unique": "A user with that username already exists."
                        },
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[
                            django.contrib.auth.validators.UnicodeUsernameValidator()
                        ],
                        verbose_name="username",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="first name"
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="last name"
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="email address"
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this account should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                # ── Custom fields ──
                ("name", models.CharField(blank=True, max_length=255)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("developer", "Developer"),
                            ("designer", "Designer"),
                            ("manager", "Manager"),
                            ("qa", "QA"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=20,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="members",
                        to="core.team",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        # ── 3. Project ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Project",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("on_hold", "On Hold"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("start_date", models.DateField(blank=True, null=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="projects",
                        to="core.team",
                    ),
                ),
            ],
        ),
        # ── 4. Task ───────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Task",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("todo", "To Do"),
                            ("in_progress", "In Progress"),
                            ("blocked", "Blocked"),
                            ("done", "Done"),
                        ],
                        default="todo",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                            ("critical", "Critical"),
                        ],
                        default="medium",
                        max_length=20,
                    ),
                ),
                ("due_date", models.DateField(blank=True, null=True)),
                ("created_by_ai", models.BooleanField(default=False)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("next_nudge_date", models.DateTimeField(blank=True, null=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasks",
                        to="core.project",
                    ),
                ),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_tasks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        # ── 5. ConversationThread ─────────────────────────────────────────────
        migrations.CreateModel(
            name="ConversationThread",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="threads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        # ── 6. ConversationMessage (with VectorField) ─────────────────────────
        migrations.CreateModel(
            name="ConversationMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("message_text", models.TextField()),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("teams", "Microsoft Teams"),
                            ("slack", "Slack"),
                            ("web", "Web"),
                            ("sms", "SMS"),
                        ],
                        default="web",
                        max_length=20,
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("interpreted", models.BooleanField(default=False)),
                (
                    "embedding",
                    pgvector.django.VectorField(blank=True, dimensions=1536, null=True),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="core.conversationthread",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="core.team",
                    ),
                ),
            ],
        ),
        # ── 7. TaskUpdate ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="TaskUpdate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("message", models.TextField()),
                (
                    "update_type",
                    models.CharField(
                        choices=[
                            ("status_change", "Status Change"),
                            ("comment", "Comment"),
                            ("assignment", "Assignment"),
                            ("ai_generated", "AI Generated"),
                        ],
                        max_length=20,
                    ),
                ),
                ("previous_status", models.CharField(blank=True, max_length=20, null=True)),
                ("new_status", models.CharField(blank=True, max_length=20, null=True)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="updates",
                        to="core.task",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        # ── 8. ProjectKnowledge (with VectorField) ────────────────────────────
        migrations.CreateModel(
            name="ProjectKnowledge",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("content", models.TextField()),
                (
                    "embedding",
                    pgvector.django.VectorField(blank=True, dimensions=1536, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="knowledge_entries",
                        to="core.project",
                    ),
                ),
                (
                    "source_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="knowledge_entries",
                        to="core.conversationmessage",
                    ),
                ),
            ],
        ),
        # ── 9. Team.managers M2M (now that User table exists) ─────────────────
        migrations.AddField(
            model_name="team",
            name="managers",
            field=models.ManyToManyField(
                blank=True,
                related_name="managed_teams",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ── 10. User.groups + user_permissions (standard AbstractUser M2M) ────
        migrations.AddField(
            model_name="user",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                related_name="user_set",
                related_query_name="user",
                to="auth.group",
                verbose_name="groups",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="user_permissions",
            field=models.ManyToManyField(
                blank=True,
                help_text="Specific permissions for this user.",
                related_name="user_set",
                related_query_name="user",
                to="auth.permission",
                verbose_name="user permissions",
            ),
        ),
    ]
