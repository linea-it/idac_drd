from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from wkfw.users.views import linea_login
from wkfw.workflow.views import AnalyticsPage, AssigneesPage, ReactPageView, ReleaseBoardPage, TemplatesPage

urlpatterns = [
    path("", ReactPageView.as_view(), name="home"),
    path("releases/<slug:slug>/", ReleaseBoardPage.as_view(), name="release-board"),
    path("templates/", TemplatesPage.as_view(), name="templates"),
    path("analytics/", AnalyticsPage.as_view(), name="analytics"),
    path("assignees/", AssigneesPage.as_view(), name="assignees"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("users/", include("wkfw.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.AUTH_SAML2_ENABLED:
    urlpatterns += [
        path("saml2/", include("djangosaml2.urls")),
        path("login/", linea_login, name="login"),
    ]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

urlpatterns += [
    path("api/", include("config.api_router")),
    path("auth-token/", obtain_auth_token),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
