from flask import Blueprint, render_template

bp = Blueprint('admin', __name__)

@bp.route('/')
def admin_home():
    return render_template('admin/admin_super.html')
