# API Contract v1 - Hestia Dashboard

This document describes the REST API endpoints used by the Hestia Dashboard frontend.

## Base URL

- **Development (Mock Mode)**: Endpoints are mocked in the frontend
- **Development (Real Backend)**: Uses Vite proxy configuration
- **Production**: Set via `VITE_API_BASE_URL` environment variable

## Authentication

All endpoints (except login) require session-based authentication via cookies.

- Session is established after successful login
- Use `credentials: "include"` in fetch requests
- 401 responses redirect to `/login`

---

## Endpoints

### Authentication

#### POST `/auth/login`

Login with email and password.

**Request**:
```
Content-Type: application/x-www-form-urlencoded

email=usuario@hotel.com&password=secreto123
```

**Response** (200):
```json
{
  "ok": true
}
```

**Response** (401):
```json
{
  "ok": false,
  "error": "Credenciales inválidas"
}
```

#### POST `/auth/logout`

Logout current session.

**Request**: No body

**Response** (200):
```json
{
  "ok": true
}
```

---

### User

#### GET `/api/me`

Get current authenticated user information.

**Response** (200):
```json
{
  "ok": true,
  "user": {
    "id": 1,
    "name": "Juan Pérez",
    "email": "juan@hotel.com",
    "role": "RECEPCION",
    "area": "MANTENCION",
    "is_superadmin": false
  }
}
```

**Response** (401):
```json
{
  "ok": false,
  "error": "No autenticado"
}
```

---

### Tickets

#### GET `/api/tickets`

List tickets with optional filters and pagination.

**Query Parameters**:
- `estado` (optional): Filter by status (`PENDIENTE`, `EN_CURSO`, `RESUELTO`, etc.)
- `prioridad` (optional): Filter by priority (`BAJA`, `MEDIA`, `ALTA`, `URGENTE`)
- `area` (optional): Filter by area (`MANTENCION`, `HOUSEKEEPING`, `ROOMSERVICE`)
- `from` (optional): Filter by creation date from (YYYY-MM-DD)
- `to` (optional): Filter by creation date to (YYYY-MM-DD)
- `assigned_to` (optional): Filter by assigned user ID
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20)

**Response** (200):
```json
{
  "items": [
    {
      "id": 42,
      "area": "MANTENCION",
      "prioridad": "ALTA",
      "estado": "PENDIENTE",
      "detalle": "Aire acondicionado no funciona",
      "ubicacion": "Habitación 305",
      "canal": "WHATSAPP",
      "created_at": "2026-01-22T10:30:00Z",
      "due_at": "2026-01-22T12:30:00Z",
      "finished_at": null,
      "is_critical": true,
      "assigned_to": 5,
      "created_by": 1,
      "org_id": 1,
      "hotel_id": 1,
      "huesped_id": "12345",
      "huesped_whatsapp": "+56912345678"
    }
  ],
  "count": 150,
  "page": 1,
  "total_pages": 8
}
```

#### GET `/api/tickets/:id`

Get details of a specific ticket.

**Status**: ⚠️ **Pending backend implementation**

**Response** (200):
```json
{
  "ok": true,
  "ticket": {
    "id": 42,
    "area": "MANTENCION",
    "prioridad": "ALTA",
    "estado": "EN_CURSO",
    "detalle": "Aire acondicionado no funciona",
    "ubicacion": "Habitación 305",
    "canal": "WHATSAPP",
    "created_at": "2026-01-22T10:30:00Z",
    "due_at": "2026-01-22T12:30:00Z",
    "finished_at": null,
    "is_critical": true,
    "assigned_to": 5,
    "created_by": 1,
    "accepted_at": "2026-01-22T10:45:00Z",
    "started_at": "2026-01-22T11:00:00Z"
  }
}
```

**Alternative**: Include ticket details in the `/api/tickets` list response.

#### GET `/api/tickets/:id/events`

Get timeline/history events for a specific ticket.

**Status**: ⚠️ **Pending backend implementation**

**Response** (200):
```json
{
  "ok": true,
  "events": [
    {
      "id": 1,
      "ticket_id": 42,
      "action": "CREADO",
      "actor_user_id": 1,
      "actor": "admin",
      "motivo": null,
      "at": "2026-01-22T10:30:00Z"
    },
    {
      "id": 2,
      "ticket_id": 42,
      "action": "ASIGNADO",
      "actor_user_id": 3,
      "actor": "supervisor",
      "motivo": "Técnico disponible",
      "at": "2026-01-22T10:35:00Z"
    },
    {
      "id": 3,
      "ticket_id": 42,
      "action": "ACEPTADO",
      "actor_user_id": 5,
      "actor": "tecnico1",
      "motivo": null,
      "at": "2026-01-22T10:45:00Z"
    }
  ]
}
```

**Alternative**: Include `events` array in the `GET /api/tickets/:id` response.

---

### Ticket Actions

These endpoints trigger state transitions for tickets. The exact implementation may vary based on your backend state machine.

#### POST `/api/tickets/:id/accept`

Accept an assigned ticket (transition from `ASIGNADO` to `ACEPTADO`).

**Request**:
```json
{
  "motivo": "Aceptado por técnico"
}
```

**Response** (200):
```json
{
  "ok": true,
  "message": "Ticket aceptado",
  "ticket_id": 42,
  "new_estado": "ACEPTADO"
}
```

#### POST `/api/tickets/:id/start`

Start working on a ticket (transition to `EN_CURSO`).

**Request**:
```json
{
  "motivo": "Iniciando reparación"
}
```

**Response** (200):
```json
{
  "ok": true,
  "message": "Ticket iniciado",
  "ticket_id": 42,
  "new_estado": "EN_CURSO"
}
```

#### POST `/api/tickets/:id/pause`

Pause work on a ticket (transition to `PAUSADO`).

**Request**:
```json
{
  "motivo": "Esperando repuesto"
}
```

**Response** (200):
```json
{
  "ok": true,
  "message": "Ticket pausado",
  "ticket_id": 42,
  "new_estado": "PAUSADO"
}
```

#### POST `/api/tickets/:id/resume`

Resume work on a paused ticket (transition back to `EN_CURSO`).

**Request**:
```json
{
  "motivo": "Repuesto disponible"
}
```

**Response** (200):
```json
{
  "ok": true,
  "message": "Ticket reanudado",
  "ticket_id": 42,
  "new_estado": "EN_CURSO"
}
```

#### POST `/api/tickets/:id/finish`

Mark ticket as resolved (transition to `RESUELTO`).

**Request**:
```json
{
  "motivo": "Aire acondicionado reparado y funcionando"
}
```

**Response** (200):
```json
{
  "ok": true,
  "message": "Ticket resuelto",
  "ticket_id": 42,
  "new_estado": "RESUELTO"
}
```

**Note**: Depending on your backend implementation, you may have a single `/api/tickets/:id/transition` endpoint that accepts the target state as a parameter instead of separate endpoints.

---

### Export

#### GET `/api/tickets/export`

Export filtered tickets to CSV or JSON format.

**Status**: ⚠️ **Currently implemented client-side only**

**Query Parameters**:
- Same filters as `GET /api/tickets`
- `format`: `csv` or `json`

**Response** (CSV):
```
Content-Type: text/csv
Content-Disposition: attachment; filename="tickets_2026-01-22.csv"

ID,Estado,Prioridad,Área,Habitación,Detalle,Asignado,Creado,Vencimiento
42,EN_CURSO,ALTA,MANTENCION,Habitación 305,Aire acondicionado no funciona,5,2026-01-22T10:30:00Z,2026-01-22T12:30:00Z
```

**Response** (JSON):
```json
Content-Type: application/json
Content-Disposition: attachment; filename="tickets_2026-01-22.json"

[
  {
    "id": 42,
    "estado": "EN_CURSO",
    ...
  }
]
```

**Current Implementation**: The frontend implements CSV/JSON export client-side using the filtered ticket data already loaded. This works well for small to medium datasets. For large datasets, consider implementing server-side export with streaming.

---

## Data Types

### User Roles
- `RECEPCION`: Reception desk staff
- `TECNICO`: Maintenance technician
- `SUPERVISOR`: Area supervisor
- `GERENTE`: Manager
- `SUPERADMIN`: System administrator

### Ticket Estados (States)
- `PENDIENTE`: Pending approval/assignment
- `PENDIENTE_APROBACION`: Pending manager approval
- `ASIGNADO`: Assigned to technician
- `ACEPTADO`: Accepted by technician
- `EN_CURSO`: Work in progress
- `PAUSADO`: Paused/on hold
- `RESUELTO`: Resolved/completed
- `DERIVADO`: Transferred to another area
- `ELIMINADO`: Deleted

### Ticket Priority
- `BAJA`: Low
- `MEDIA`: Medium
- `ALTA`: High
- `URGENTE`: Urgent

### Ticket Areas
- `MANTENCION`: Maintenance
- `HOUSEKEEPING`: Housekeeping
- `ROOMSERVICE`: Room Service

---

## Error Handling

All endpoints follow a consistent error response format:

```json
{
  "ok": false,
  "error": "Human-readable error message"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad request (invalid parameters)
- `401`: Unauthorized (not logged in)
- `403`: Forbidden (insufficient permissions)
- `404`: Not found
- `500`: Internal server error

---

## Notes

- All timestamps are in ISO 8601 format (UTC)
- Session timeout: 24 hours of inactivity (configurable)
- CORS is configured for development proxy
- Production should use HTTPS only
