from django.urls import path
from rest_framework.routers import DefaultRouter

from idac_drd.workflow.api.views import (
    ActivityViewSet,
    BottleneckAnalyticsView,
    DataReleaseViewSet,
    ExternalIdentityViewSet,
    GitHubOptionsView,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="api-users")
router.register("external-identities", ExternalIdentityViewSet, basename="api-external-identities")
router.register("releases", DataReleaseViewSet, basename="api-releases")
router.register("activities", ActivityViewSet, basename="api-activities")

urlpatterns = router.urls + [
    path(
        "analytics/bottlenecks/",
        BottleneckAnalyticsView.as_view(),
        name="api-bottlenecks",
    ),
    path(
        "github/options/",
        GitHubOptionsView.as_view(),
        name="api-github-options",
    ),
]
