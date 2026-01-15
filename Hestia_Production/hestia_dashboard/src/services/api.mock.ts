/**
 * Mock API service - mirrors Flask backend responses exactly
 * Used when VITE_USE_MOCKS=true
 */

import type {
    MeResponse,
    TicketsListParams,
    TicketsListResponse,
    TicketDetailResponse,
    TicketEventsResponse,
    TicketActionResponse,
    TicketActionType,
    Ticket,
    TicketEvent,
    User,
} from '../types/api';

// Simulate async delay
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Mock session state (simulates Flask session cookie)
let mockUser: User | null = null;

// Mock data matching Flask backend structure
const MOCK_TICKETS: Ticket[] = [
    {
        id: 1,
        area: 'MANTENCION',
        prioridad: 'ALTA',
        estado: 'ASIGNADO',
        detalle: 'Reparar aire acondicionado habitación 305',
        ubicacion: 'Habitación 305',
        canal: 'recepcion',
        created_at: '2026-01-15T10:30:00',
        due_at: '2026-01-15T14:00:00',
        finished_at: null,
        is_critical: false,
        assigned_to: 5,
        created_by: 1,
    },
    {
        id: 2,
        area: 'HOUSEKEEPING',
        prioridad: 'MEDIA',
        estado: 'PENDIENTE',
        detalle: 'Limpieza profunda habitación 201',
        ubicacion: 'Habitación 201',
        canal: 'huesped_whatsapp',
        created_at: '2026-01-15T11:15:00',
        due_at: '2026-01-15T16:00:00',
        finished_at: null,
        is_critical: false,
        assigned_to: null,
        created_by: 1,
    },
    {
        id: 3,
        area: 'MANTENCION',
        prioridad: 'URGENTE',
        estado: 'EN_CURSO',
        detalle: 'Fuga de agua en baño principal',
        ubicacion: 'Suite 405',
        canal: 'recepcion',
        created_at: '2026-01-15T09:00:00',
        due_at: '2026-01-15T11:00:00',
        finished_at: null,
        is_critical: true,
        assigned_to: 6,
        created_by: 1,
    },
    {
        id: 4,
        area: 'ROOMSERVICE',
        prioridad: 'BAJA',
        estado: 'RESUELTO',
        detalle: 'Pedido de toallas extra',
        ubicacion: 'Habitación 102',
        canal: 'roomservice_llamada',
        created_at: '2026-01-14T18:30:00',
        due_at: '2026-01-14T19:00:00',
        finished_at: '2026-01-14T18:45:00',
        is_critical: false,
        assigned_to: 7,
        created_by: 2,
    },
    {
        id: 5,
        area: 'HOUSEKEEPING',
        prioridad: 'ALTA',
        estado: 'PAUSADO',
        detalle: 'Cambio de sábanas y limpieza general',
        ubicacion: 'Habitación 310',
        canal: 'housekeeping_whatsapp',
        created_at: '2026-01-15T08:00:00',
        due_at: '2026-01-15T12:00:00',
        finished_at: null,
        is_critical: false,
        assigned_to: 8,
        created_by: 1,
    },
];

const MOCK_EVENTS: Record<number, TicketEvent[]> = {
    1: [
        {
            id: 1,
            ticket_id: 1,
            action: 'CREADO',
            actor_user_id: 1,
            actor: 'recepcion.user',
            motivo: null,
            at: '2026-01-15T10:30:00',
        },
        {
            id: 2,
            ticket_id: 1,
            action: 'ASIGNADO',
            actor_user_id: 1,
            actor: 'recepcion.user',
            motivo: null,
            at: '2026-01-15T10:32:00',
        },
    ],
    3: [
        {
            id: 5,
            ticket_id: 3,
            action: 'CREADO',
            actor_user_id: 1,
            actor: 'recepcion.user',
            motivo: null,
            at: '2026-01-15T09:00:00',
        },
        {
            id: 6,
            ticket_id: 3,
            action: 'ASIGNADO',
            actor_user_id: 1,
            actor: 'recepcion.user',
            motivo: null,
            at: '2026-01-15T09:02:00',
        },
        {
            id: 7,
            ticket_id: 3,
            action: 'ACEPTADO',
            actor_user_id: 6,
            actor: 'carlos.tecnico',
            motivo: null,
            at: '2026-01-15T09:10:00',
        },
        {
            id: 8,
            ticket_id: 3,
            action: 'INICIADO',
            actor_user_id: 6,
            actor: 'carlos.tecnico',
            motivo: null,
            at: '2026-01-15T09:15:00',
        },
    ],
    5: [
        {
            id: 9,
            ticket_id: 5,
            action: 'CREADO',
            actor_user_id: 1,
            actor: 'recepcion.user',
            motivo: null,
            at: '2026-01-15T08:00:00',
        },
        {
            id: 10,
            ticket_id: 5,
            action: 'PAUSADO',
            actor_user_id: 8,
            actor: 'maria.housekeeping',
            motivo: 'Esperando aprobación del supervisor',
            at: '2026-01-15T10:00:00',
        },
    ],
};

// ==================== Mock API Methods ====================

export async function login(
    email: string,
    password: string
): Promise<{ ok: boolean }> {
    await delay(300);

    // Accept demo credentials or any email/password for mock
    if (
        (email === 'demo@hestia.local' && password === 'demo') ||
        (email && password)
    ) {
        mockUser = {
            id: 1,
            name: 'Usuario Demo',
            email: email,
            role: 'RECEPCION',
            area: 'MANTENCION',
            is_superadmin: false,
        };
        return { ok: true };
    }

    throw new Error('Credenciales inválidas');
}

export async function logout(): Promise<void> {
    await delay(100);
    mockUser = null;
}

export async function getMe(): Promise<MeResponse> {
    await delay(200);

    if (!mockUser) {
        return {
            ok: false,
            error: 'No autenticado',
        };
    }

    return {
        ok: true,
        user: mockUser,
    };
}

export async function getTickets(
    params: TicketsListParams = {}
): Promise<TicketsListResponse> {
    await delay(400);

    let filtered = [...MOCK_TICKETS];

    // Filter by estado (backend mapping)
    if (params.estado === 'PENDIENTE') {
        filtered = filtered.filter((t) =>
            ['PENDIENTE', 'PENDIENTE_APROBACION'].includes(t.estado)
        );
    } else if (params.estado) {
        filtered = filtered.filter((t) => t.estado === params.estado);
    }

    // Filter by period (simplified - just check created_at)
    if (params.period && params.period !== 'all') {
        const filterDate = new Date();

        if (params.period === 'today') {
            filterDate.setHours(0, 0, 0, 0);
        } else if (params.period === 'yesterday') {
            filterDate.setDate(filterDate.getDate() - 1);
            filterDate.setHours(0, 0, 0, 0);
        } else if (params.period === '7d') {
            filterDate.setDate(filterDate.getDate() - 7);
        } else if (params.period === '30d') {
            filterDate.setDate(filterDate.getDate() - 30);
        }

        filtered = filtered.filter((t) => {
            const createdAt = new Date(t.created_at);
            return createdAt >= filterDate;
        });
    }

    // Apply limit
    const limit = params.limit || 50;
    filtered = filtered.slice(0, limit);

    return {
        items: filtered,
        count: filtered.length,
    };
}

export async function getTicketById(
    id: number
): Promise<TicketDetailResponse> {
    await delay(300);

    const ticket = MOCK_TICKETS.find((t) => t.id === id);

    if (!ticket) {
        return {
            ok: false,
            error: 'Ticket no encontrado',
        };
    }

    return {
        ok: true,
        ticket,
    };
}

export async function getTicketEvents(
    id: number
): Promise<TicketEventsResponse> {
    await delay(300);

    const events = MOCK_EVENTS[id] || [];

    return {
        ok: true,
        events,
    };
}

export async function updateTicketState(
    id: number,
    action: TicketActionType,
    motivo?: string
): Promise<TicketActionResponse> {
    await delay(500);

    const ticket = MOCK_TICKETS.find((t) => t.id === id);

    if (!ticket) {
        return {
            ok: false,
            error: 'Ticket no encontrado',
        };
    }

    // Validate state transitions (simplified, matches Flask ALLOWED_TRANSITIONS)
    const validTransitions: Record<TicketActionType, string[]> = {
        accept: ['PENDIENTE', 'ASIGNADO', 'DERIVADO'],
        start: ['ACEPTADO'],
        pause: ['EN_CURSO'],
        resume: ['PAUSADO'],
        finish: ['EN_CURSO'],
    };

    if (!validTransitions[action].includes(ticket.estado)) {
        return {
            ok: false,
            error: `No puedes ${action} un ticket en estado ${ticket.estado}`,
        };
    }

    // Update estado
    const newEstados: Record<TicketActionType, typeof ticket.estado> = {
        accept: 'ACEPTADO',
        start: 'EN_CURSO',
        pause: 'PAUSADO',
        resume: 'EN_CURSO',
        finish: 'RESUELTO',
    };

    ticket.estado = newEstados[action];

    // Add event to mock history
    const newEvent: TicketEvent = {
        id: Date.now(),
        ticket_id: id,
        action: action.toUpperCase() as TicketEvent['action'],
        actor_user_id: mockUser?.id,
        actor: mockUser?.name || 'sistema',
        motivo: motivo || null,
        at: new Date().toISOString(),
    };

    if (!MOCK_EVENTS[id]) {
        MOCK_EVENTS[id] = [];
    }
    MOCK_EVENTS[id].push(newEvent);

    return {
        ok: true,
        message: `Ticket ${action === 'finish' ? 'resuelto' : action === 'pause' ? 'pausado' : action === 'resume' ? 'reanudado' : action === 'start' ? 'iniciado' : 'aceptado'}.`,
        ticket_id: id,
        new_estado: ticket.estado,
    };
}
