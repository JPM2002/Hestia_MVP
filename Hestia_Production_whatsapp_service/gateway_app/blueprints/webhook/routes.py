# gateway_app/blueprints/webhook/routes.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import (
    current_app,
    jsonify,
    render_template,
    request,
)

from . import bp  # <- use the shared blueprint

from gateway_app.config import cfg
from gateway_app.services import audio as audio_svc
from gateway_app.services import whatsapp_api
from gateway_app.core import state as state_machine
