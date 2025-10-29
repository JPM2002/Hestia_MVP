def sla_minutes(area: str, prioridad: str) -> int: return 30
def compute_due(created_at, area, prioridad): return created_at
def is_critical(now, due_at): return False
def date_key(dt): return dt.strftime('%Y-%m-%d')
