# hestia_app/core/device.py
from flask import request, g, current_app, render_template
from user_agents import parse as parse_ua

def _is_mobile(ua_str: str) -> bool:
    if not ua_str:
        return False
    try:
        ua = parse_ua(ua_str)
        return ua.is_mobile or ua.is_tablet
    except Exception:
        return False

def render_best(template_name: str, **ctx):
    """
    If g.view_mode == 'mobile', try a *_m.html variant; else fallback to the base template.
    Example: 'tickets/list.html' -> 'tickets/list_m.html'
    """
    if getattr(g, "view_mode", "desktop") == "mobile":
        if "." in template_name:
            base, ext = template_name.rsplit(".", 1)
            mobile_name = f"{base}_m.{ext}"
        else:
            mobile_name = f"{template_name}_m.html"

        loader = current_app.jinja_loader
        if loader:
            try:
                loader.get_source(current_app.jinja_env, mobile_name)
                return render_template(mobile_name, **ctx)
            except Exception:
                pass
    return render_template(template_name, **ctx)

def register_device_hooks(app):
    """
    - Sets g.view_mode = 'mobile' or 'desktop' based on cookie, ?view=, or User-Agent.
    - Persists explicit ?view= choice into a 'view' cookie.
    - Injects {is_mobile, view_mode, render_best} into templates.
    """
    @app.before_request
    def _ua_to_g():
        q_view = request.args.get("view")
        if q_view in ("mobile", "desktop"):
            g.view_mode = q_view
            g._set_view_cookie = q_view
        else:
            c_view = request.cookies.get("view")
            if c_view in ("mobile", "desktop"):
                g.view_mode = c_view
            else:
                ua = request.headers.get("User-Agent", "")
                g.view_mode = "mobile" if _is_mobile(ua) else "desktop"
        g.is_mobile = (g.view_mode == "mobile")

    @app.after_request
    def _persist_view(resp):
        val = getattr(g, "_set_view_cookie", None)
        if val:
            resp.set_cookie("view", val, max_age=60*60*24*365, httponly=False, samesite="Lax")
        return resp

    @app.context_processor
    def _inject():
        return {
            "is_mobile": getattr(g, "is_mobile", False),
            "view_mode": getattr(g, "view_mode", "desktop"),
            "render_best": render_best,
        }
