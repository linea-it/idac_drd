from django.views.generic import TemplateView


class ReactPageView(TemplateView):
    page = "releases"
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page"] = self.page
        ctx["release_slug"] = self.kwargs.get("slug", "")
        return ctx


class ReleaseBoardPage(ReactPageView):
    page = "board"
    template_name = "pages/release_board.html"


class TemplatesPage(ReactPageView):
    page = "templates"
    template_name = "pages/templates.html"


class AnalyticsPage(ReactPageView):
    page = "analytics"
    template_name = "pages/analytics.html"


class AssigneesPage(ReactPageView):
    page = "assignees"
    template_name = "pages/assignees.html"
