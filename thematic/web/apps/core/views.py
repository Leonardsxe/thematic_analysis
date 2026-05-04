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

    Sets the language cookie and rewrites the redirect URL to include
    the correct i18n prefix (e.g. /es/corpus/ ↔ /corpus/).
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        from django.conf import settings
        from django.shortcuts import redirect
        from django.utils.translation import check_for_language

        lang = request.POST.get("language", "en")
        next_url = request.POST.get("next", "/")

        if not next_url:
            next_url = "/"

        if check_for_language(lang):
            # Rewrite URL prefix for i18n_patterns
            try:
                from django.urls import translate_url
                next_url = translate_url(next_url, lang)
            except Exception:
                pass

            response = redirect(next_url)
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                lang,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
            return response

        return redirect(next_url)
