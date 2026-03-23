from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    ConversationMessage,
    ConversationThread,
    Project,
    ProjectKnowledge,
    Task,
    TaskUpdate,
    Team,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Nudge Profile", {"fields": ("name", "team", "role")}),
    )
    list_display = ["username", "name", "email", "team", "role", "is_staff"]
    list_filter = ["role", "team", "is_staff", "is_active"]
    search_fields = ["username", "name", "email"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "member_count"]
    search_fields = ["name"]
    filter_horizontal = ["managers"]

    def member_count(self, obj):
        return obj.members.count()

    member_count.short_description = "Members"


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "team", "status", "start_date", "due_date"]
    list_filter = ["status", "team"]
    search_fields = ["name", "description"]
    date_hierarchy = "due_date"


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title",
        "project",
        "assignee",
        "status",
        "priority",
        "due_date",
        "created_by_ai",
        "last_updated",
    ]
    list_filter = ["status", "priority", "created_by_ai", "project"]
    search_fields = ["title", "description"]
    date_hierarchy = "due_date"
    raw_id_fields = ["assignee", "project"]


@admin.register(ConversationThread)
class ConversationThreadAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "created_at"]
    list_filter = ["user"]
    date_hierarchy = "created_at"


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "team", "source", "timestamp", "interpreted"]
    list_filter = ["source", "interpreted", "team"]
    search_fields = ["message_text"]
    date_hierarchy = "timestamp"
    readonly_fields = ["timestamp", "embedding"]


@admin.register(TaskUpdate)
class TaskUpdateAdmin(admin.ModelAdmin):
    list_display = ["id", "task", "user", "update_type", "previous_status", "new_status", "timestamp"]
    list_filter = ["update_type"]
    search_fields = ["message"]
    date_hierarchy = "timestamp"
    raw_id_fields = ["task", "user"]


@admin.register(ProjectKnowledge)
class ProjectKnowledgeAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "created_at", "content_preview"]
    list_filter = ["project"]
    search_fields = ["content"]
    date_hierarchy = "created_at"
    readonly_fields = ["created_at", "embedding"]

    def content_preview(self, obj):
        return obj.content[:80] + "..." if len(obj.content) > 80 else obj.content

    content_preview.short_description = "Content"
