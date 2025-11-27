# gateway_app/__init__.py
"""
Application factory for the Hestia WhatsApp gateway service.
"""

from __future__ import annotations

import logging

from flask import Flask

from gateway_app.config import cfg
from gateway_app.filters import register_filters
from gateway_app.logging_cfg import configure_logging
