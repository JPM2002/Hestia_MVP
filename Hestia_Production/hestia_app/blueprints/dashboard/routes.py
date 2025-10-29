from flask import Blueprint, render_template, redirect, url_for

bp = Blueprint('dashboards', __name__)

@bp.route('/')
def root():
    return redirect(url_for('dashboards.dashboard_home'))

@bp.route('/home')
def dashboard_home():
    return render_template('dashboards/dashboard_gerente.html')
