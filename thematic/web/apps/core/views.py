"""apps/core/views.py"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
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
    body: language=es|en, next=/current/path

    Sets the language cookie and redirects to the language-prefixed
    equivalent of the current URL so LocaleMiddleware reads the prefix
    on the next request (required because prefix_default_language=True).
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        from django.conf import settings as django_settings
        from django.shortcuts import redirect
        from django.utils.translation import check_for_language

        lang = request.POST.get("language", "en")
        next_url = request.POST.get("next", "/")
        if not next_url or next_url == "None":
            next_url = "/"

        if check_for_language(lang):
            # translate_url rewrites /en/corpus/ → /es/corpus/ (or vice-versa)
            try:
                from django.urls import translate_url
                next_url = translate_url(next_url, lang)
            except Exception:
                # Fallback: redirect to language root
                next_url = f"/{lang}/"

            response = redirect(next_url)
            # Also set cookie so LocaleMiddleware has a fallback
            response.set_cookie(
                django_settings.LANGUAGE_COOKIE_NAME,  # "django_language"
                lang,
                max_age=365 * 24 * 60 * 60,  # 1 year
                path="/",
                samesite="Lax",
            )
            return response

        return redirect(next_url or "/")