"""apps/core/views.py"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.translation import check_for_language, get_language
from django.views import View
from django.views.generic import TemplateView

from thematic.web.apps.core import services


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        llm = services.get_llm()
        ctx["ollama_available"] = (
            llm.is_available() if llm and hasattr(llm, "is_available") else False
        )
        return ctx


class SetLanguageView(View):
    """
    POST /lang/
    body: language=es  (or 'en')

    Stores the chosen language in the session and redirects back.
    Django's LocaleMiddleware will pick it up on the next request.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        lang = request.POST.get("language", "en")
        next_url = request.POST.get("next", request.META.get("HTTP_REFERER", "/"))

        if check_for_language(lang):
            request.session["_language"] = lang
            # Django's LocaleMiddleware reads LANGUAGE_SESSION_KEY
            from django.utils.translation import LANGUAGE_SESSION_KEY  # type: ignore[attr-defined]
            try:
                request.session[LANGUAGE_SESSION_KEY] = lang
            except AttributeError:
                # LANGUAGE_SESSION_KEY removed in Django 5 — session key is "_language"
                pass

        return redirect(next_url)
