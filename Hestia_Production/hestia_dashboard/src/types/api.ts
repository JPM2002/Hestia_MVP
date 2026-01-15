// API Response Types based on Flask backend structure
export interface ApiResponse<T> {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}

// User types matching Flask session structure
export interface User {
  id: number;
  name: string;
  email: string;
  role: 'RECEPCION' | 'TECNICO' | 'SUPERVISOR' | 'GERENTE';
  area?: 'MANTENCION' | 'HOUSEKEEPING' | 'ROOMSERVICE';
  is_superadmin: boolean;
}

// Ticket types matching Flask Tickets table
export type TicketPrioridad = 'BAJA' | 'MEDIA' | 'ALTA' | 'URGENTE';
export type TicketEstado =
  | 'PENDIENTE'
  | 'PENDIENTE_APROBACION'
  | 'ASIGNADO'
  | 'ACEPTADO'
  | 'EN_CURSO'
  | 'PAUSADO'
  | 'DERIVADO'
  | 'RESUELTO'
  | 'ELIMINADO';
export type TicketArea = 'MANTENCION' | 'HOUSEKEEPING' | 'ROOMSERVICE';

export interface Ticket {
  id: number;
  area: TicketArea;
  prioridad: TicketPrioridad;
  estado: TicketEstado;
  detalle: string;
  ubicacion: string | null;
  canal: string | null;
  created_at: string; // ISO 8601
  due_at: string | null; // ISO 8601
  finished_at: string | null; // ISO 8601
  is_critical: boolean;
  assigned_to?: number | null;
  created_by?: number;
  org_id?: number;
  hotel_id?: number;
  huesped_id?: string | null;
  huesped_whatsapp?: string | null;
  accepted_at?: string | null;
  started_at?: string | null;
  confidence_score?: number | null;
  qr_required?: boolean;
}

// Timeline event types matching Flask TicketHistory table
export type TicketAction =
  | 'CREADO'
  | 'ASIGNADO'
  | 'REASIGNADO'
  | 'ACEPTADO'
  | 'INICIADO'
  | 'PAUSADO'
  | 'REANUDADO'
  | 'RESUELTO'
  | 'DERIVADO'
  | 'EDITADO'
  | 'ELIMINADO';

export interface TicketEvent {
  id?: number;
  ticket_id: number;
  action: TicketAction;
  actor_user_id?: number | null;
  actor: string; // username
  motivo?: string | null;
  at: string; // ISO 8601 timestamp
  area?: string;
  ubicacion?: string;
}

// API request/response types

// GET /api/me
export interface MeResponse extends ApiResponse<User> {
  user?: User;
}

// GET /api/recepcion/list
export interface TicketsListResponse {
  items: Ticket[];
  count: number;
}

export interface TicketsListParams {
  estado?: 'PENDIENTE' | 'EN_CURSO' | 'RESUELTO' | '';
  period?: 'today' | 'yesterday' | '7d' | '30d' | 'all';
  limit?: number;
}

// GET /api/tickets/<id> (MOCK)
export interface TicketDetailResponse extends ApiResponse<Ticket> {
  ticket?: Ticket;
}

// GET /api/tickets/<id>/events (MOCK)
export interface TicketEventsResponse extends ApiResponse<TicketEvent[]> {
  events?: TicketEvent[];
}

// POST /tickets/<id>/{action}
export interface TicketActionResponse extends ApiResponse<unknown> {
  message?: string;
  ticket_id?: number;
  new_estado?: TicketEstado;
}

export type TicketActionType = 'accept' | 'start' | 'pause' | 'resume' | 'finish';
