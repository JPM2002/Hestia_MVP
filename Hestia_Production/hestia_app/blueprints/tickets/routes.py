from flask import Blueprint, render_template

bp = Blueprint('tickets', __name__)

@bp.route('/')
def list_tickets():
    tickets = []  # TODO: fetch from DB
    return render_template('tickets/tickets.html', tickets=tickets)
