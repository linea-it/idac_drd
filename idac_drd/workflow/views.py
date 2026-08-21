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


class DraftsPage(ReactPageView):
    page = "drafts"


class ArchivedPage(ReactPageView):
    page = "archived"
