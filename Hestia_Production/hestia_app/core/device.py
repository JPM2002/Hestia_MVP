from flask import request, g, render_template
try:
    from user_agents import parse as parse_ua
except Exception:
    parse_ua = None

MOBILE_COOKIE = "view_mode"  # 'mobile'|'desktop'|'auto'

def _detect_device_from_ua(ua_string: str) -> dict:
    if not parse_ua:
        return {"class":"desktop","is_mobile":False,"is_tablet":False,"is_desktop":True}
    ua = parse_ua(ua_string or "")
    if ua.is_mobile and not ua.is_tablet:
        cls = "mobile"
    elif ua.is_tablet:
        cls = "tablet"
    else:
        cls = "desktop"
    return {"class": cls, "is_mobile": cls=="mobile", "is_tablet": cls=="tablet", "is_desktop": cls=="desktop"}

def _decide_view_mode(req):
    q = (req.args.get("view") or "").lower()
    if q in ("mobile","desktop","auto"):
        g._set_view_cookie = q
        if q != "auto": return q
    cv = (req.cookies.get(MOBILE_COOKIE) or "").lower()
    if cv in ("mobile","desktop"):
        return cv
    dev = _detect_device_from_ua(req.headers.get("User-Agent",""))
    return "mobile" if dev["is_mobile"] else "desktop"

def before_request():
    dev = _detect_device_from_ua(request.headers.get("User-Agent",""))
    g.device = dev
    g.view_mode = _decide_view_mode(request)

def after_request(resp):
    v = getattr(g, "_set_view_cookie", None)
    if v:
        resp.set_cookie(MOBILE_COOKIE, v, max_age=30*24*3600, samesite="Lax")
    return resp

def render_best(templates: list[str], **ctx):
    last = templates[-1]
    for name in templates:
        try:
            return render_template(name, **ctx)
        except Exception:
            continue
    return render_template(last, **ctx)

def register_device_hooks(app):
    app.before_request(before_request)
    app.after_request(after_request)
