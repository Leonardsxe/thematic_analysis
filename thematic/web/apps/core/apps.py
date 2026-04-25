"""apps/core/apps.py"""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "thematic.web.apps.core"
    label = "thematic_core"
    verbose_name = "Thematic Core"

    def ready(self) -> None:
        """Wire all infrastructure once at server startup."""
        from thematic.web.apps.core import services
        services._bootstrap()
