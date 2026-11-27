"""
@file __init__.py
@description Local Web UI package for SQL Doctor (sqld ui)
@module sqldoctor/ui
"""

from sqldoctor.ui.server import create_ui_app, run_ui_server

__all__ = ["create_ui_app", "run_ui_server"]
