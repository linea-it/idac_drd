import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView

User = get_user_model()


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        return self.request.user.get_absolute_url()

    def get_object(self):
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse("users:detail", kwargs={"username": self.request.user.username})


user_redirect_view = UserRedirectView.as_view()


def linea_login(request):
    return render(request, "pages/linea_login.html")


def saml2_template_failure(request, exception=None, status=403, **kwargs):
    logger = logging.getLogger("djangosaml2")
    logger.info("saml2_template_failure() exception=%s", exception)

    idp_name = request.session.get("idp_name")
    needs_registration = request.session.get("needs_registration", False)
    user_status = request.session.get("user_status")

    if needs_registration:
        if idp_name == "rubin_oidc":
            return render(
                request,
                "djangosaml2/rubin_need_registration.html",
                {"exception": exception},
                status=status,
            )
        return render(
            request,
            "djangosaml2/linea_need_registration.html",
            {"exception": exception},
            status=status,
        )

    if user_status in ["PendingApproval", "Pending"]:
        return render(
            request,
            "djangosaml2/waiting_approval.html",
            {"exception": exception},
            status=status,
        )

    return render(request, "djangosaml2/login_error.html", {"exception": exception}, status=status)
