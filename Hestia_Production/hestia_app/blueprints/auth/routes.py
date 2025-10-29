from flask import Blueprint, render_template, request, redirect, url_for, session

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # TODO: replace with real auth
        session['user'] = {'id': 1, 'name': 'Demo', 'role': 'GERENTE'}
        return redirect(url_for('dashboards.dashboard_home'))
    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
