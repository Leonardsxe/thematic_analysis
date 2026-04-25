from django.urls import path
from . import views

app_name = "corpus"

urlpatterns = [
    path("", views.CorpusView.as_view(), name="index"),
    path("import/", views.ImportView.as_view(), name="import"),
    path("sources/", views.SourceListView.as_view(), name="sources"),
]
