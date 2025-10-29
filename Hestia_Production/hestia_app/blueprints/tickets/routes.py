from flask import Blueprint, render_template

bp = Blueprint(
    "tickets",
    __name__,
    url_prefix="/tickets",           # ← clave: ya no ocupa "/"
    template_folder="templates"
)

@bp.get("/", endpoint="tickets")     # ahora url_for('tickets') es /tickets
def list_tickets():
    tickets = []  # stub
    return render_template("tickets/tickets.html", tickets=tickets)

@bp.get("/create", endpoint="ticket_create")  # coincide con base.html
def create_ticket():
    return "Formulario de nuevo ticket (pendiente)"
