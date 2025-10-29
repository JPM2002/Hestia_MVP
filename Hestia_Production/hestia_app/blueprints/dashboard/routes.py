from __future__ import annotations
from datetime import datetime, timedelta
from random import randint, choice
from flask import render_template, jsonify, request
from . import bp

# ---------------------------- dashboards ----------------------------
@app.route('/dashboard')
def dashboard():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    if user.get('is_superadmin'):
        return redirect(url_for('admin_super'))

    role = current_org_role() or user.get('role')
    if role == 'GERENTE':
        kpis, charts = get_global_kpis()
        return render_template('dashboard_gerente.html', user=user, kpis=kpis, charts=charts)

    if role == 'SUPERVISOR':
        kpis, tickets = get_area_data(None)  # UI puede filtrar por área
        return render_template('dashboard_supervisor.html', user=user, kpis=kpis, tickets=tickets)

    # In your /dashboard route, replace the RECEPTION block with:
    if role == 'RECEPCION':
        return redirect(url_for('recepcion_dashboard'))

        # TECNICO / others
    if role == 'TECNICO':
        # pick a default area for the technician
        area = default_area_for_user()
        slug = area_slug(area)
        view = g.view_mode  # 'mobile' or 'desktop'
        # pull tickets for that area
        tickets = get_assigned_tickets_for_area(user['id'], area)

        # Try specialized templates first, then fall back.
        # Create any of these files if you want unique UIs:
        #   templates/tecnico_<area>_mobile.html
        #   templates/tecnico_<area>_desktop.html
        #   templates/tecnico_mobile.html
        #   templates/tecnico_desktop.html
        # Fallback to your existing generic: dashboard_tecnico.html
        template_order = [
            f"tecnico_{slug}_{view}.html",
            f"tecnico_{view}.html",
            "dashboard_tecnico.html",
        ]
        return render_best(template_order, user=user, tickets=tickets, area=area, device=g.device, view=view)

    # default (non-recognized roles) => generic technician page for now
    tickets = get_assigned_tickets(user['id'])
    return render_template('dashboard_tecnico.html', user=user, tickets=tickets)
