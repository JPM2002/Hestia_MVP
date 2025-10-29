# hestia_app/services/tickets.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from .db import fetchall, fetchone, execute, insert_and_get_id

def get_tickets(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Get tickets with optional filters.
    """
    filters = filters or {}
    
    where_conditions = []
    params = []
    
    if filters.get("q"):
        where_conditions.append("(detalle LIKE ? OR ubicacion LIKE ? OR huesped_id LIKE ?)")
        search_term = f"%{filters['q']}%"
        params.extend([search_term, search_term, search_term])
    
    if filters.get("area"):
        where_conditions.append("area = ?")
        params.append(filters["area"])
    
    if filters.get("prioridad"):
        where_conditions.append("prioridad = ?")
        params.append(filters["prioridad"])
    
    if filters.get("estado"):
        where_conditions.append("estado = ?")
        params.append(filters["estado"])
    
    # Period filter
    if filters.get("period") == "today":
        where_conditions.append("DATE(created_at) = DATE('now')")
    elif filters.get("period") == "yesterday":
        where_conditions.append("DATE(created_at) = DATE('now', '-1 day')")
    elif filters.get("period") == "7d":
        where_conditions.append("created_at >= datetime('now', '-7 days')")
    elif filters.get("period") == "30d":
        where_conditions.append("created_at >= datetime('now', '-30 days')")
    
    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
    
    query = f"""
    SELECT t.*, 
           u.username as assigned_username,
           c.username as created_username
    FROM Tickets t
    LEFT JOIN Users u ON t.assigned_to = u.id
    LEFT JOIN Users c ON t.created_by = c.id
    WHERE {where_clause}
    ORDER BY t.created_at DESC
    """
    
    try:
        rows = fetchall(query, params)
        return [dict(row) for row in rows]
    except Exception:
        # Return empty list if database is not available
        return []

def get_tickets_by_user(user_id: int, area: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get tickets assigned to a specific user.
    """
    where_conditions = ["assigned_to = ?"]
    params = [user_id]
    
    if area:
        where_conditions.append("area = ?")
        params.append(area)
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    SELECT t.*, 
           u.username as assigned_username,
           c.username as created_username
    FROM Tickets t
    LEFT JOIN Users u ON t.assigned_to = u.id
    LEFT JOIN Users c ON t.created_by = c.id
    WHERE {where_clause}
    ORDER BY t.created_at DESC
    """
    
    try:
        rows = fetchall(query, params)
        return [dict(row) for row in rows]
    except Exception:
        return []

def create_ticket(data: Dict[str, Any]) -> int:
    """
    Create a new ticket and return its ID.
    """
    query = """
    INSERT INTO Tickets (
        area, prioridad, estado, detalle, canal_origen, ubicacion,
        huesped_id, created_at, due_at, assigned_to, created_by,
        confidence_score, qr_required
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    params = (
        data.get("area"),
        data.get("prioridad"),
        data.get("estado", "PENDIENTE"),
        data.get("detalle"),
        data.get("canal"),
        data.get("ubicacion"),
        data.get("huesped_id"),
        data.get("created_at"),
        data.get("due_at"),
        data.get("assigned_to"),
        data.get("created_by"),
        data.get("confidence_score"),
        data.get("qr_required", 0)
    )
    
    try:
        ticket_id = insert_and_get_id(query, params)
        
        # Add to ticket history
        add_ticket_history(ticket_id, "CREADO", data.get("created_by"))
        
        return ticket_id
    except Exception:
        return 0

def update_ticket_state(ticket_id: int, new_state: str, 
                       motivo: Optional[str] = None,
                       user_id: Optional[int] = None) -> bool:
    """
    Update ticket state and add to history.
    """
    # Get current ticket info
    ticket = fetchone("SELECT * FROM Tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        return False
    
    # Update ticket
    update_fields = ["estado = ?"]
    params = [new_state]
    
    now = datetime.now(timezone.utc).isoformat()
    
    if new_state == "ACEPTADO":
        update_fields.append("accepted_at = ?")
        params.append(now)
    elif new_state == "EN_CURSO":
        update_fields.append("started_at = ?")
        params.append(now)
    elif new_state == "RESUELTO":
        update_fields.append("finished_at = ?")
        params.append(now)
    
    params.append(ticket_id)
    
    query = f"UPDATE Tickets SET {', '.join(update_fields)} WHERE id = ?"
    
    try:
        execute(query, params)
        
        # Add to history
        add_ticket_history(ticket_id, new_state, user_id, motivo)
        
        return True
    except Exception:
        return False

def assign_ticket(ticket_id: int, user_id: int, assigned_by: Optional[int] = None) -> bool:
    """
    Assign ticket to a user.
    """
    query = "UPDATE Tickets SET assigned_to = ?, estado = 'ASIGNADO' WHERE id = ?"
    
    try:
        execute(query, (user_id, ticket_id))
        add_ticket_history(ticket_id, "ASIGNADO", assigned_by)
        return True
    except Exception:
        return False

def add_ticket_history(ticket_id: int, action: str, 
                      actor_user_id: Optional[int] = None,
                      motivo: Optional[str] = None) -> bool:
    """
    Add entry to ticket history.
    """
    query = """
    INSERT INTO TicketHistory (ticket_id, actor_user_id, action, motivo, at)
    VALUES (?, ?, ?, ?, ?)
    """
    
    params = (
        ticket_id,
        actor_user_id,
        action,
        motivo,
        datetime.now(timezone.utc).isoformat()
    )
    
    try:
        execute(query, params)
        return True
    except Exception:
        return False

def get_ticket_history(ticket_id: int) -> List[Dict[str, Any]]:
    """
    Get ticket history.
    """
    query = """
    SELECT h.*, u.username as actor_username
    FROM TicketHistory h
    LEFT JOIN Users u ON h.actor_user_id = u.id
    WHERE h.ticket_id = ?
    ORDER BY h.at ASC
    """
    
    try:
        rows = fetchall(query, (ticket_id,))
        return [dict(row) for row in rows]
    except Exception:
        return []
