from rest_framework import serializers

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


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "name",
            "team",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    """Used when creating a new user — accepts a password."""

    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "name", "team", "role", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class TeamSerializer(serializers.ModelSerializer):
    managers = UserSerializer(many=True, read_only=True)
    manager_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
        write_only=True,
        source="managers",
        required=False,
    )
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ["id", "name", "managers", "manager_ids", "member_count"]

    def get_member_count(self, obj):
        return obj.members.count()


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "team",
            "status",
            "start_date",
            "due_date",
        ]


class TaskSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "project",
            "assignee",
            "assignee_detail",
            "status",
            "priority",
            "due_date",
            "created_by_ai",
            "last_updated",
            "next_nudge_date",
        ]
        read_only_fields = ["last_updated"]


class ConversationThreadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationThread
        fields = ["id", "user", "created_at"]
        read_only_fields = ["created_at"]


class ConversationMessageSerializer(serializers.ModelSerializer):
    # Exclude the embedding vector from API responses — it's large and internal
    class Meta:
        model = ConversationMessage
        fields = [
            "id",
            "thread",
            "user",
            "team",
            "message_text",
            "source",
            "timestamp",
            "interpreted",
        ]
        read_only_fields = ["timestamp", "interpreted"]


class ConversationMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ["id", "thread", "user", "team", "message_text", "source"]


class TaskUpdateSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)

    class Meta:
        model = TaskUpdate
        fields = [
            "id",
            "task",
            "user",
            "user_detail",
            "message",
            "update_type",
            "previous_status",
            "new_status",
            "timestamp",
        ]
        read_only_fields = ["timestamp"]


class ProjectKnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectKnowledge
        fields = ["id", "project", "content", "source_message", "created_at"]
        read_only_fields = ["created_at"]


# ─── AI endpoint request/response serializers ─────────────────────────────────

class InterpretRequestSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    message = serializers.CharField()


class InterpretResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    response = serializers.CharField()
    actions_taken = serializers.ListField(child=serializers.DictField(), required=False)
    error = serializers.CharField(required=False)


class AIActionResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.DictField(required=False)
