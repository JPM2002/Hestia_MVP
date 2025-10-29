# shift.py
from __future__ import annotations
from datetime import datetime, timezone
from flask import session, jsonify

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _shift_log_append(action: str):
    log = session.get('hk_shift_log') or []
    at = _now_iso()
    log.append({"action": action, "at": at})
    session['hk_shift_log'] = log[-50:]
    session.modified = True
    return at

def _shift_state():
    s = session.get('hk_shift') or {}
    started_at = s.get('started_at')
    ended_at   = s.get('ended_at')
    paused     = bool(s.get('paused'))
    active     = bool(started_at and not ended_at and not paused)
    return {
        "active": active,
        "paused": paused,
        "started_at": started_at,
        "ended_at": ended_at,
    }

def _hk_shift_active() -> bool:
    s = session.get('hk_shift') or {}
    return bool(s.get('started_at')) and not s.get('ended_at') and not s.get('paused', False)

def init_shift(app):
    @app.context_processor
    def inject_hk_flags():
        return {"HK_SHIFT_ACTIVE": _shift_state()["active"]}

    @app.get('/api/hk/shift')
    def hk_shift_status():
        state = _shift_state()
        state['log'] = session.get('hk_shift_log', [])
        return jsonify(state)

    @app.post('/hk/shift/start')
    def hk_shift_start():
        session['hk_shift_log'] = []
        started = _shift_log_append('START')
        session['hk_shift'] = {"started_at": started, "paused": False, "ended_at": None}
        session.modified = True
        return ('', 204)

    @app.post('/hk/shift/pause')
    def hk_shift_pause():
        s = session.get('hk_shift') or {}
        if not s.get('started_at') or s.get('ended_at'):
            return ('', 204)
        s['paused'] = not s.get('paused', False)
        _shift_log_append('PAUSE' if s['paused'] else 'RESUME')
        session['hk_shift'] = s
        session.modified = True
        return ('', 204)

    @app.post('/hk/shift/end')
    def hk_shift_end():
        s = session.get('hk_shift') or {}
        if not s.get('started_at') or s.get('ended_at'):
            return ('', 204)
        ended = _shift_log_append('END')
        s['ended_at'] = ended
        s['paused'] = False
        session['hk_shift'] = s
        session.modified = True
        return ('', 204)
