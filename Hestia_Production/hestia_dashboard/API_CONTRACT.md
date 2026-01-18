# API Contract & Client Documentation

## Overview

The Hestia Dashboard uses a centralized API client (`src/api/client.ts`) for all HTTP requests to the Flask backend. This document describes the **real backend endpoints** as implemented in the Flask application.

## Environment Configuration

### Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `""` (empty) | Base URL for API requests. Leave empty to use Vite proxy (same-origin). |
| `VITE_USE_MOCKS` | `true` | Enable mock data mode. Set to `false` for real backend calls. |

### Examples

**Development (with proxy):**
```env
VITE_API_BASE_URL=
VITE_USE_MOCKS=false
```

**Development (with mocks):**
```env
VITE_API_BASE_URL=
VITE_USE_MOCKS=true
```

**Production:**
```env
VITE_API_BASE_URL=https://api.hestia.com
VITE_USE_MOCKS=false
```

---

## Real Backend Endpoints

### Authentication

#### POST `/login`
**Proxied as:** `/auth/login` (Vite strips `/auth` prefix)

Login with email/username and password. Uses cookie-based session.

**Request:**
```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

email=user@example.com&password=mypassword
```

**Response (Success):**
- **Status:** 302 (redirect to dashboard) or 200
- Session cookie set automatically

**Response (Error):**
```json
{
  "error": "Credenciales inválidas o usuario inactivo."
}
```

**Frontend Usage:**
```typescript
import { loginRequest } from '../api/client';

const result = await loginRequest(email, password);
// { ok: true }
```

---

#### GET `/logout`
**Proxied as:** `/auth/logout` (Vite strips `/auth` prefix)

Clears session and logs out user.

**Request:**
```http
GET /auth/logout
```

**Response:**
- **Status:** 302 (redirect to login)
- Session cookie cleared

**Frontend Usage:**
```typescript
import { logoutRequest } from '../api/client';

await logoutRequest();
```

---

### Recepción Dashboard

#### GET `/api/recepcion/list`
**Proxied as:** `/api/recepcion/list` (no rewrite)

Get filtered list of tickets with pagination.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `estado` | string | - | Filter by state: `PENDIENTE`, `EN_CURSO`, `RESUELTO` |
| `period` | string | `today` | Time filter: `today`, `yesterday`, `7d`, `30d`, `all` |
| `limit` | number | `50` | Max results to return |

**Request:**
```http
GET /api/recepcion/list?estado=PENDIENTE&period=today&limit=50
```

**Response:**
```json
{
  "items": [
    {
      "id": 123,
      "area": "MANTENCION",
      "prioridad": "ALTA",
      "estado": "PENDIENTE",
      "detalle": "Aire acondicionado no funciona",
      "ubicacion": "Habitación 305",
      "created_at": "2026-01-15T10:30:00",
      "due_at": "2026-01-15T12:30:00",
      "finished_at": null,
      "canal": "huesped_whatsapp",
      "is_critical": false
    }
  ],
  "count": 1
}
```

**Frontend Usage:**
```typescript
import { getTickets } from '../services/api';

const response = await getTickets({
  estado: 'PENDIENTE',
  period: 'today',
  limit: 50
});
Console.log(response.items);
```

---

#### GET `/api/recepcion/kpis`
**Proxied as:** `/api/recepcion/kpis` (no rewrite)

Get dashboard KPIs for reception.

**Request:**
```http
GET /api/recepcion/kpis
```

**Response:**
```json
{
  "pending": 12,
  "in_progress": 5,
  "resolved_today": 8,
  "critical": 2,
  "at": "2026-01-15T14:30:00"
}
```

---

### Ticket Operations

All ticket transition endpoints use the `/tickets/<id>/<action>` pattern.

**Proxy Configuration:** These are proxied as `/ops/tickets/<id>/<action>` (Vite strips `/ops` prefix)

---

#### POST `/tickets/<id>/accept`
**Proxied as:** `/ops/tickets/<id>/accept`

Technician accepts an assigned ticket.

**Request:**
```http
POST /ops/tickets/123/accept
Content-Type: application/x-www-form-urlencoded

(no body required)
```

**Response:**
```json
{
  "ok": true,
  "message": "Ticket aceptado.",
  "ticket_id": 123,
  "new_estado": "ACEPTADO"
}
```

**Allowed States:** `PENDIENTE`, `ASIGNADO`, `DERIVADO` → `ACEPTADO`

---

#### POST `/tickets/<id>/start`
**Proxied as:** `/ops/tickets/<id>/start`

Start working on an accepted ticket.

**Request:**
```http
POST /ops/tickets/123/start
```

**Response:**
```json
{
  "ok": true,
  "message": "Ticket iniciado.",
  "ticket_id": 123,
  "new_estado": "EN_CURSO"
}
```

**Allowed States:** `ACEPTADO` → `EN_CURSO`

---

#### POST `/tickets/<id>/pause`
**Proxied as:** `/ops/tickets/<id>/pause`

Pause an in-progress ticket.

**Request:**
```http
POST /ops/tickets/123/pause
Content-Type: application/x-www-form-urlencoded

motivo=Falta%20de%20repuestos
```

**Parameters:**
- `motivo` (optional): Reason for pausing

**Response:**
```json
{
  "ok": true,
  "message": "Ticket pausado.",
  "ticket_id": 123,
  "new_estado": "PAUSADO"
}
```

**Allowed States:** `EN_CURSO` → `PAUSADO`

---

#### POST `/tickets/<id>/resume`
**Proxied as:** `/ops/tickets/<id>/resume`

Resume a paused ticket.

**Request:**
```http
POST /ops/tickets/123/resume
```

**Response:**
```json
{
  "ok": true,
  "message": "Ticket reanudado.",
  "ticket_id": 123,
  "new_estado": "EN_CURSO"
}
```

**Allowed States:** `PAUSADO` → `EN_CURSO`

---

#### POST `/tickets/<id>/finish`
**Proxied as:** `/ops/tickets/<id>/finish`

Mark ticket as resolved/finished.

**Request:**
```http
POST /ops/tickets/123/finish
Content-Type: application/x-www-form-urlencoded

motivo=Completado%20satisfactoriamente
```

**Parameters:**
- `motivo` (optional): Completion notes

**Response:**
```json
{
  "ok": true,
  "message": "Ticket finalizado.",
  "ticket_id": 123,
  "new_estado": "RESUELTO"
}
```

**Allowed States:** `EN_CURSO` → `RESUELTO`

---

## Vite Proxy Configuration

The dev server (`vite.config.ts`) proxies API requests to `http://localhost:5000`:

| Frontend Path | Backend Path | Notes |
|---------------|--------------|-------|
| `/auth/login` | `/login` | Strips `/auth` prefix |
| `/auth/logout` | `/logout` | Strips `/auth` prefix |
| `/ops/tickets/<id>/<action>` | `/tickets/<id>/<action>` | Strips `/ops` prefix |
| `/api/*` | `/api/*` | No rewrite |

**Why prefixes?**
- Avoids conflicts with React Router SPA routes (`/login`, `/tickets`)
- Vite proxy rewrites strip the prefix before forwarding to Flask

---

## Client Error Handling

Errors are categorized by HTTP status:

| Status | Type | User Message |
|--------|------|--------------|
| 401 | `auth` | "Sesión expirada" → Auto-redirect to `/login` after 2s |
| 403 | `forbidden` | "Sin permisos" |
| 500+ | `server` | "Error del servidor" |
| Network | `network` | "Error de conexión" |

All errors display via the `ErrorToast` component with auto-hide (5s).

---

##Manual Testing Checklist

### 1. Proxy + Credentials Test
```bash
# Terminal 1: Start Flask backend
cd hestia_app
flask run --port 5000

# Terminal 2: Start Vite dev server
cd hestia_dashboard
npm run dev
```

**Steps:**
1. Open `http://localhost:5173/login`
2. Enter valid credentials
3. Check Network tab: request goes to `/auth/login`, cookie is set
4. Verify redirect to `/tickets`

**Expected:** Login successful, session cookie visible in DevTools

---

### 2. Error Toast Test (401)
**Steps:**
1. Clear cookies in DevTools (Application → Cookies → Delete all)
2. Try to access `/api/recepcion/list` directly
3. Watch for error toast

**Expected:** 
- Toast appears with "Sesión expirada" message
- Auto-redirect to `/login` after 2s

---

### 3. Tickets List Test
**Steps:**
1. Login successfully
2. Navigate to `/tickets`
3. Open DevTools Network tab
4. Check request to `/api/recepcion/list`

**Expected:**
- Request includes `credentials: include`
- Response returns tickets array
- No CORS errors

---

### 4. Ticket Transition Test
**Steps:**
1. From tickets list, click "Aceptar" on a pending ticket
2. Check Network tab for request to `/ops/tickets/<id>/accept`

**Expected:**
- POST request with `credentials: include`
- Response `{ ok: true }`
- Ticket state updates in UI

---

### 5. Error Toast Test (500)
**Steps:**
1. Stop Flask backend (Ctrl+C)
2. Try to load tickets list
3. Watch for error toast

**Expected:**
- Toast appears with "Error de conexión" or "Error del servidor"
- Toast auto-hides after 5s

---

## Notes

- All requests use cookie-based authentication with `credentials: "include"`
- Session cookies are automatically sent and managed by the browser
- The client supports both JSON and form-urlencoded payloads
- Error messages are user-friendly and localized (Spanish)
- Mock mode (`VITE_USE_MOCKS=true`) bypasses all backend calls for offline development

