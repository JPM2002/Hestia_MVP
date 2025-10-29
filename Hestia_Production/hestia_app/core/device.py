from flask import request, g, render_template
try:
    from user_agents import parse as parse_ua
except Exception:
    parse_ua = None

# device.py - for device detection and view mode
# ---------------------------- Device detection ----------------------------
MOBILE_COOKIE = "view_mode"   # 'mobile' | 'desktop' | 'auto'

def _detect_device_from_ua(ua_string: str) -> dict:
    try:
        ua = parse_ua(ua_string or "")
        # "mobile" includes phones; tablets we treat separately
        if ua.is_mobile and not ua.is_tablet:
            cls = "mobile"
        elif ua.is_tablet:
            cls = "tablet"
        else:
            cls = "desktop"
        return {"class": cls, "is_mobile": cls == "mobile", "is_tablet": cls == "tablet", "is_desktop": cls == "desktop"}
    except Exception:
        return {"class":"desktop","is_mobile":False,"is_tablet":False,"is_desktop":True}

def _decide_view_mode(req):
    # 1) explicit ?view=mobile|desktop|auto overrides (and we persist via cookie)
    q = (req.args.get("view") or "").lower()
    if q in ("mobile","desktop","auto"):
        g._set_view_cookie = q
        if q != "auto":
            return q

    # 2) cookie
    cv = (req.cookies.get(MOBILE_COOKIE) or "").lower()
    if cv in ("mobile","desktop"):
        return cv

    # 3) auto from UA
    dev = _detect_device_from_ua(req.headers.get("User-Agent",""))
    return "mobile" if dev["is_mobile"] else "desktop"

@app.before_request
def _inject_device():
    dev = _detect_device_from_ua(request.headers.get("User-Agent",""))
    g.device = dev
    g.view_mode = _decide_view_mode(request)   # 'mobile' | 'desktop'

@app.after_request
def _persist_view_cookie(resp):
    # Set cookie only when query override was used
    v = getattr(g, "_set_view_cookie", None)
    if v:
        resp.set_cookie(MOBILE_COOKIE, v, max_age=30*24*3600, samesite="Lax")
    return resp

def render_best(templates: list[str], **ctx):
    """Try templates in order; fall back to last item if none found."""
    last = templates[-1]
    for name in templates:
        try:
            return render_template(name, **ctx)
        except TemplateNotFound:
            continue
    return render_template(last, **ctx)
