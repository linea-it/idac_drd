from django.urls import path
from rest_framework.routers import DefaultRouter

from wkfw.workflow.api.views import (
    ActivityViewSet,
    BottleneckAnalyticsView,
    DataReleaseViewSet,
    UserViewSet,
    WorkflowTemplateViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="api-users")
router.register("templates", WorkflowTemplateViewSet, basename="api-templates")
router.register("releases", DataReleaseViewSet, basename="api-releases")
router.register("activities", ActivityViewSet, basename="api-activities")

urlpatterns = router.urls + [
    path("analytics/bottlenecks/", BottleneckAnalyticsView.as_view(), name="api-bottlenecks"),
]
