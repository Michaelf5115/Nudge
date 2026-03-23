from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ConversationMessage,
    ConversationThread,
    Project,
    Task,
    TaskUpdate,
    Team,
    User,
)
from .serializers import (
    AIActionResponseSerializer,
    ConversationMessageCreateSerializer,
    ConversationMessageSerializer,
    ConversationThreadSerializer,
    InterpretRequestSerializer,
    ProjectSerializer,
    TaskSerializer,
    TaskUpdateSerializer,
    TeamSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from .services.ai_service import (
    check_up_for_user,
    generate_project_summary,
    interpret_user_message,
    poke_user,
    update_manager,
)


# ─── Core resource ViewSets ───────────────────────────────────────────────────


class TeamViewSet(viewsets.ModelViewSet):
    """CRUD for Teams. Managers are set via manager_ids."""

    queryset = Team.objects.prefetch_related("managers", "members").all()
    serializer_class = TeamSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]
    ordering = ["name"]


class UserViewSet(viewsets.ModelViewSet):
    """CRUD for Users."""

    queryset = User.objects.select_related("team").all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["team", "role", "is_active"]
    search_fields = ["username", "name", "email"]
    ordering_fields = ["username", "name", "date_joined"]
    ordering = ["username"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    """CRUD for Projects. Filter by team and status."""

    queryset = Project.objects.select_related("team").all()
    serializer_class = ProjectSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["team", "status"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "due_date", "start_date", "status"]
    ordering = ["name"]


class TaskViewSet(viewsets.ModelViewSet):
    """
    CRUD for Tasks.
    Filter by project, assignee, status, and priority.

    Custom actions:
      POST /api/tasks/{id}/complete/  — mark task as done
      POST /api/tasks/{id}/assign/    — assign to a user
    """

    queryset = (
        Task.objects.select_related("project", "assignee")
        .prefetch_related("updates")
        .all()
    )
    serializer_class = TaskSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["project", "assignee", "status", "priority", "created_by_ai"]
    search_fields = ["title", "description"]
    ordering_fields = ["due_date", "priority", "status", "last_updated"]
    ordering = ["-last_updated"]

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Mark a task as done and record a TaskUpdate."""
        task = self.get_object()
        previous_status = task.status
        task.status = Task.Status.DONE
        task.save(update_fields=["status", "last_updated"])

        TaskUpdate.objects.create(
            task=task,
            user=request.user,
            message="Task marked as completed.",
            update_type=TaskUpdate.UpdateType.STATUS_CHANGE,
            previous_status=previous_status,
            new_status=Task.Status.DONE,
        )

        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        """
        Assign a task to a user.
        Body: { "assignee_id": <int> }
        """
        task = self.get_object()
        assignee_id = request.data.get("assignee_id")
        if not assignee_id:
            return Response(
                {"error": "assignee_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignee = get_object_or_404(User, pk=assignee_id)
        previous_assignee = str(task.assignee) if task.assignee else "unassigned"
        task.assignee = assignee
        task.save(update_fields=["assignee", "last_updated"])

        TaskUpdate.objects.create(
            task=task,
            user=request.user,
            message=f"Task assigned from {previous_assignee} to {assignee}.",
            update_type=TaskUpdate.UpdateType.ASSIGNMENT,
        )

        return Response(TaskSerializer(task).data)


class ConversationMessageViewSet(viewsets.ModelViewSet):
    """
    List and create conversation messages.
    Custom action:
      POST /api/conversations/messages/{id}/interpret/  — run AI interpretation pipeline
    """

    queryset = ConversationMessage.objects.select_related("user", "team", "thread").all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["thread", "user", "team", "source", "interpreted"]
    ordering_fields = ["timestamp"]
    ordering = ["-timestamp"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ConversationMessageCreateSerializer
        return ConversationMessageSerializer

    @action(detail=True, methods=["post"], url_path="interpret")
    def interpret(self, request, pk=None):
        """
        Trigger the AI interpretation pipeline for a single message.
        Sets interpreted=True on success.
        """
        message_obj = self.get_object()

        if message_obj.interpreted:
            return Response(
                {"detail": "Message has already been interpreted."},
                status=status.HTTP_200_OK,
            )

        result = interpret_user_message(
            user_id=message_obj.user_id,
            message=message_obj.message_text,
        )

        if result.get("success"):
            message_obj.interpreted = True
            message_obj.save(update_fields=["interpreted"])

        return Response(result)


class TaskUpdateViewSet(viewsets.ReadOnlyModelViewSet):
    """List task updates. Filter by task."""

    queryset = TaskUpdate.objects.select_related("task", "user").all()
    serializer_class = TaskUpdateSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["task", "update_type"]
    ordering_fields = ["timestamp"]
    ordering = ["-timestamp"]


# ─── AI endpoint views ────────────────────────────────────────────────────────


class AIInterpretView(APIView):
    """
    POST /api/ai/interpret/

    Main AI entry point. Accepts a user_id and message, runs the full
    interpret_user_message pipeline and returns the AI response plus any
    actions taken.

    Body: { "user_id": <int>, "message": "<string>" }
    """

    def post(self, request):
        serializer = InterpretRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        result = interpret_user_message(
            user_id=serializer.validated_data["user_id"],
            message=serializer.validated_data["message"],
        )
        return Response(result)


class AICheckInView(APIView):
    """
    POST /api/ai/check-in/{user_id}/

    Triggers a proactive check-in for the specified user — the AI reviews
    their open tasks and sends a status prompt if appropriate.
    """

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        result = check_up_for_user(user)
        return Response(result)


class AIPokeView(APIView):
    """
    POST /api/ai/poke/{user_id}/

    Sends a poke/nudge to a user who has stale tasks or upcoming deadlines,
    prompting them to provide a status update.
    """

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        result = poke_user(user)
        return Response(result)


class AIManagerUpdateView(APIView):
    """
    POST /api/ai/manager-update/{manager_id}/

    Generates and delivers a team status summary to the specified manager,
    covering all active projects and outstanding task blockers.
    """

    def post(self, request, manager_id):
        manager = get_object_or_404(User, pk=manager_id)
        result = update_manager(manager)
        return Response(result)


class AIProjectSummaryView(APIView):
    """
    POST /api/ai/project-summary/{project_id}/

    Generates a human-readable project summary using the project's tasks,
    recent activity, and knowledge repository entries.
    """

    def post(self, request, project_id):
        from .models import Project as ProjectModel

        project = get_object_or_404(ProjectModel, pk=project_id)
        result = generate_project_summary(project)
        return Response(result)
