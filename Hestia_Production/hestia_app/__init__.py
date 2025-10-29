# core wiring
from .core.timefmt import register_jinja_filters
from .core.device import init_device
from .core.errors import register_db_error_handlers
from .core.shift import init_shift
from .core.rbac import init_rbac_helpers
from .core.area import init_area

register_jinja_filters(app)
init_device(app)
register_db_error_handlers(app)
init_shift(app)

# Provide DB + scope callables to RBAC & Area modules
def _current_scope():
    return session.get('org_id'), session.get('hotel_id')

init_rbac_helpers(app, fetchone_fn=fetchone, fetchall_fn=fetchall, current_scope_fn=_current_scope)
init_area(fetchone_fn=fetchone, current_scope_fn=_current_scope)
