from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AICheckInView,
    AIInterpretView,
    AIManagerUpdateView,
    AIPokeView,
    AIProjectSummaryView,
    ConversationMessageViewSet,
    ProjectViewSet,
    TaskUpdateViewSet,
    TaskViewSet,
    TeamViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"users", UserViewSet, basename="user")
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"conversations/messages", ConversationMessageViewSet, basename="message")
router.register(r"task-updates", TaskUpdateViewSet, basename="taskupdate")

urlpatterns = [
    # Resource CRUD (router-generated)
    path("", include(router.urls)),

    # AI endpoints
    path("ai/interpret/", AIInterpretView.as_view(), name="ai-interpret"),
    path("ai/check-in/<int:user_id>/", AICheckInView.as_view(), name="ai-check-in"),
    path("ai/poke/<int:user_id>/", AIPokeView.as_view(), name="ai-poke"),
    path("ai/manager-update/<int:manager_id>/", AIManagerUpdateView.as_view(), name="ai-manager-update"),
    path("ai/project-summary/<int:project_id>/", AIProjectSummaryView.as_view(), name="ai-project-summary"),
]
