from flask import (
    render_template, request, redirect, url_for, flash, session
)
from werkzeug.routing import BuildError
from werkzeug.security import check_password_hash
from . import bp

# Intento de integrar tu capa de DB real; si no está, seguimos con stubs.
try:
    from hestia_app.services.db import get_db  # Debe retornar conexión (sqlite3 / psycopg2)
except Exception:
    get_db = None

# Detección de dispositivo (opcional): si user_agents no está, hacemos un fallback simple
try:
    from user_agents import parse as parse_ua
except Exception:
    parse_ua = None


# -----------------------------
# Helpers
# -----------------------------
def _goto_dashboard_fallback():
    """Redirige al dashboard si existe; si no, a '/'. Evita romper si aún no registraste ese endpoint."""
    try:
        # Ajusta si tu blueprint de dashboard expone endpoint "dashboard"
        return redirect(url_for("dashboard.dashboard"))
    except BuildError:
        try:
            # Algunas apps usan endpoint raíz simple
            return redirect(url_for("dashboard"))
        except BuildError:
            return redirect("/")

def _query_user_by_login(login_text):
    """
    Busca usuario por email o username.
    Retorna dict con id, email, username, base_role, password / password_hash si existen.
    """
    if get_db is None:
        return None

    q = """
    SELECT id, email, username, base_role,
           password, password_hash
    FROM users
    WHERE email = ? OR username = ?
    LIMIT 1
    """
    try:
        con = get_db()
        cur = con.execute(q, (login_text, login_text))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))
    except Exception as e:
        flash(f"DB error: {e}", "warning")
        return None

def _password_ok(user_row, plain_password):
    """Soporta password hash (password_hash) o texto plano (password)."""
    if not user_row:
        return False
    # Primero intenta hash
    ph = user_row.get("password_hash")
    if ph:
        try:
            return check_password_hash(ph, plain_password)
        except Exception:
            pass
    # Fallback: columna password en texto plano
    p = user_row.get("password")
    if p is None:
        return False
    return str(p) == str(plain_password)

def _is_mobile(req):
    """Heurística de móvil. Usa user_agents si está disponible; si no, UA básico."""
    if parse_ua:
        ua = parse_ua(req.headers.get("User-Agent", ""))
        return ua.is_mobile or ua.is_tablet
    # Fallback ingenuo
    ua_str = (req.user_agent.string or "").lower()
    return any(token in ua_str for token in ["mobile", "iphone", "android", "ipad"])


# -----------------------------
# Rutas
# -----------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Renderiza formulario de login y procesa autenticación.
    Variables de template soportadas por login.html:
      - message (str)
      - success (bool)
      - enable_demo (bool)
    """
    enable_demo = True  # Puedes mover esto a app.config["ENABLE_TECH_DEMO"]

    if request.method == "POST":
        login_text = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Modo demo si no hay DB: acepta admin/demo123
        if get_db is None:
            if login_text and password and password == "demo123":
                session["user_id"] = 1
                session["username"] = login_text
                session["base_role"] = "GERENTE"
                flash("Sesión iniciada (demo sin DB).", "success")
                return _goto_dashboard_fallback()
            else:
                return render_template(
                    "auth/login.html",
                    message="Credenciales inválidas (modo demo acepta *cualquiera*/demo123).",
                    success=False,
                    enable_demo=enable_demo,
                )

        # DB real
        user = _query_user_by_login(login_text)
        if not user or not _password_ok(user, password):
            return render_template(
                "auth/login.html",
                message="Email/usuario o contraseña incorrectos.",
                success=False,
                enable_demo=enable_demo,
            )

        # Guarda sesión mínima
        session["user_id"] = user["id"]
        session["username"] = user.get("username") or user.get("email")
        session["base_role"] = user.get("base_role") or "USUARIO"

        flash("Bienvenido 👋", "success")
        return _goto_dashboard_fallback()

    # GET
    return render_template("auth/login.html", enable_demo=enable_demo)


@bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/demo/tecnico", methods=["GET"])
def demo_tecnico():
    """
    Muestra layouts técnicos sin requerir login ni DB.
    Parámetros:
      - area: MANTENCION | HOUSEKEEPING | ROOMSERVICE (opcional)
      - view: auto | mobile | desktop  (auto por defecto)
    """
    area = request.args.get("area") or "MANTENCION"
    view = (request.args.get("view") or "auto").lower()

    # Decide vista
    if view == "auto":
        is_m = _is_mobile(request)
    elif view == "mobile":
        is_m = True
    elif view == "desktop":
        is_m = False
    else:
        is_m = _is_mobile(request)

    # Plantillas existentes en tu árbol:
    #   tecnico_desktop.html
    #   tecnico_mobile.html
    #   tecnico_mobile_list.html
    #   tecnico_housekeeping_mobile.html
    #   tecnico_mantencion_mobile.html
    #   tecnico_roomservice_mobile.html
    #
    # Regla simple:
    # - Si mobile + área específica => usa plantilla específica del área si existe,
    #   de lo contrario cae a tecnico_mobile.html
    # - Si desktop => tecnico_desktop.html
    if not is_m:
        tpl = "tecnico/tecnico_desktop.html"
    else:
        area_map = {
            "MANTENCION": "tecnico/tecnico_mantencion_mobile.html",
            "HOUSEKEEPING": "tecnico/tecnico_housekeeping_mobile.html",
            "ROOMSERVICE": "tecnico/tecnico_roomservice_mobile.html",
        }
        tpl = area_map.get(area.upper(), "tecnico/tecnico_mobile.html")

    # Render directo (no depende de DB)
    return render_template(tpl, area=area, demo=True)
