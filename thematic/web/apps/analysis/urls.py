from django.urls import path
from . import views

app_name = "analysis"

urlpatterns = [
    path("immersion/", views.ImmersionView.as_view(), name="immersion"),
    path("clusters/", views.ClustersView.as_view(), name="clusters"),
    path("comparison/", views.ComparisonView.as_view(), name="comparison"),
]
