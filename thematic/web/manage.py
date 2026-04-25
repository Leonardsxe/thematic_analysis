#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

Run from the project root (directory containing pyproject.toml):

    python thematic/web/manage.py runserver
    python thematic/web/manage.py compilemessages
    python thematic/web/manage.py collectstatic
"""
import os
import sys
from pathlib import Path


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "thematic.web.config.settings")

    # Ensure the project root is on sys.path so `thematic.*` is importable
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Run: pip install django whitenoise"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
