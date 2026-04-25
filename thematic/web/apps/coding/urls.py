from django.urls import path
from . import views

app_name = "coding"

urlpatterns = [
    path("", views.CodingView.as_view(), name="index"),
    path("codebook/", views.CodebookView.as_view(), name="codebook"),
]
