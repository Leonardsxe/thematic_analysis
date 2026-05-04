"""apps/core/api_urls.py — AJAX endpoint routing"""
from django.urls import path

from thematic.web.apps.coding import api as coding_api
from thematic.web.apps.corpus import api as corpus_api

urlpatterns = [
    # Corpus
    path("corpus/import/", corpus_api.ImportTranscriptView.as_view(), name="api_import"),

    # Coding
    path("coding/apply/", coding_api.ApplyCodeView.as_view(), name="api_apply_code"),
    path("coding/suggest/", coding_api.SuggestCodesView.as_view(), name="api_suggest_codes"),
    path("coding/accept/", coding_api.AcceptSuggestionView.as_view(), name="api_accept_suggestion"),
    path("coding/reject/", coding_api.RejectSuggestionView.as_view(), name="api_reject_suggestion"),

    # Segments
    path("segments/similar/", coding_api.FindSimilarView.as_view(), name="api_find_similar"),
    path("coding/excerpts/", coding_api.ExcerptsView.as_view(), name="api_excerpts"),

    # Categories & Themes
    path("codebook/categories/", coding_api.CreateCategoryView.as_view(), name="api_create_category"),
    path("codebook/assign/", coding_api.AssignCodeToCategoryView.as_view(), name="api_assign_category"),
    path("themes/save/", coding_api.SaveThemeView.as_view(), name="api_save_theme"),
    path("themes/<str:theme_id>/publish/", coding_api.PublishThemeView.as_view(), name="api_publish_theme"),
]
