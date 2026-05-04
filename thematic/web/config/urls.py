"""
config/urls.py — Root URL configuration
========================================

URL layout
----------
  /                       → dashboard (core)
  /en/  /es/              → language prefix (django.conf.urls.i18n)
  /corpus/                → corpus management
  /immersion/             → immersion reader
  /coding/                → coding workspace
  /codebook/              → codebook management
  /clusters/              → cluster explorer
  /comparison/            → cross-source comparison
  /export/                → export centre
  /api/                   → AJAX endpoints (JSON)
  /lang/<code>/           → language switcher (POST)
"""

from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path

from thematic.web.apps.core import views as core_views

# ── Language-prefixed routes ──────────────────────────────────────────────────
urlpatterns = i18n_patterns(
    path("", core_views.DashboardView.as_view(), name="dashboard"),
    path("corpus/", include("thematic.web.apps.corpus.urls")),
    path("coding/", include("thematic.web.apps.coding.urls")),
    path("analysis/", include("thematic.web.apps.analysis.urls")),
    path("export/", include("thematic.web.apps.export.urls")),
    prefix_default_language=True,  # /en/ and /es/ — lets LocaleMiddleware read path prefix
)

# ── Non-prefixed routes (AJAX, language switch) ───────────────────────────────
urlpatterns += [
    path("api/", include("thematic.web.apps.core.api_urls")),
    path("lang/", core_views.SetLanguageView.as_view(), name="set_language"),
]