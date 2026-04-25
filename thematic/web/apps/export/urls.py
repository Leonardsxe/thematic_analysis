from django.urls import path
from . import views

app_name = "export"

urlpatterns = [
    path("", views.ExportView.as_view(), name="index"),
    path("matrix/", views.DownloadMatrixView.as_view(), name="matrix"),
    path("codebook/", views.DownloadCodebookView.as_view(), name="codebook"),
    path("audit/", views.DownloadAuditView.as_view(), name="audit"),
]
