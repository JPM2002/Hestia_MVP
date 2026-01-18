// hestia_dashboard/src/services/api.ts
import type {
    MeResponse,
    TicketsListParams,
    TicketsListResponse,
    TicketDetailResponse,
    TicketEventsResponse,
    TicketActionResponse,
    TicketActionType,
    MetricsParams,
    MetricsSummaryResponse,
    MetricsQualityResponse,
} from '../types/api';
import { loginRequest, logoutRequest, get, postForm } from '../api/client';

// Environment variables (Vite)
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

// ==================== API Methods ====================

/**
 * POST /auth/login - Cookie-based session login
 * Proxied to Flask /login via Vite rewrite
 */
export async function login(
    email: string,
    password: string
): Promise<{ ok: boolean }> {
    if (USE_MOCKS) {
        const { login: mockLogin } = await import('./api.mock.ts');
        return mockLogin(email, password);
    }

    return loginRequest(email, password);
}

/**
 * GET /auth/logout - Clear session
 * Proxied to Flask /logout via Vite rewrite
 */
export async function logout(): Promise<void> {
    if (USE_MOCKS) {
        const { logout: mockLogout } = await import('./api.mock.ts');
        return mockLogout();
    }

    return logoutRequest();
}

/**
 * GET /api/me - Validate session and get current user
 * NOTE: This endpoint DOES NOT EXIST in backend - will use mock
 */
export async function getMe(): Promise<MeResponse> {
    if (USE_MOCKS) {
        const { getMe: mockGetMe } = await import('./api.mock.ts');
        return mockGetMe();
    }

    // TODO: Backend needs to implement this endpoint
    return get<MeResponse>('/api/me');
}

/**
 * GET /api/recepcion/list - Get tickets list with filters
 */
export async function getTickets(
    params: TicketsListParams = {}
): Promise<TicketsListResponse> {
    if (USE_MOCKS) {
        const { getTickets: mockGetTickets } = await import('./api.mock.ts');
        return mockGetTickets(params);
    }

    const queryParams = new URLSearchParams();
    if (params.estado) queryParams.set('estado', params.estado);
    if (params.period) queryParams.set('period', params.period);
    if (params.limit) queryParams.set('limit', params.limit.toString());

    const query = queryParams.toString();
    const endpoint = `/api/recepcion/list${query ? `?${query}` : ''}`;

    return get<TicketsListResponse>(endpoint);
}

/**
 * GET /api/tickets/<id> - Get ticket detail
 * NOTE: This endpoint DOES NOT EXIST in backend - will use mock
 */
export async function getTicketById(id: number): Promise<TicketDetailResponse> {
    if (USE_MOCKS) {
        const { getTicketById: mockGetTicketById } = await import('./api.mock.ts');
        return mockGetTicketById(id);
    }

    // TODO: Backend needs to implement this endpoint
    return get<TicketDetailResponse>(`/api/tickets/${id}`);
}

/**
 * GET /api/tickets/<id>/events - Get ticket timeline
 * NOTE: This endpoint DOES NOT EXIST in backend - will use mock
 */
export async function getTicketEvents(
    id: number
): Promise<TicketEventsResponse> {
    if (USE_MOCKS) {
        const { getTicketEvents: mockGetTicketEvents } = await import(
            './api.mock.ts'
        );
        return mockGetTicketEvents(id);
    }

    // TODO: Backend needs to implement this endpoint
    return get<TicketEventsResponse>(`/api/tickets/${id}/events`);
}

/**
 * POST /ops/tickets/<id>/{action} - Update ticket state
 * Proxied to Flask /tickets/<id>/{action} via Vite rewrite
 * Actions: accept, start, pause, resume, finish
 */
export async function updateTicketState(
    id: number,
    action: TicketActionType,
    motivo?: string
): Promise<TicketActionResponse> {
    if (USE_MOCKS) {
        const { updateTicketState: mockUpdateTicketState } = await import(
            './api.mock.ts'
        );
        return mockUpdateTicketState(id, action, motivo);
    }

    const data: Record<string, string> = {};
    if (motivo) {
        data.motivo = motivo;
    }

    return postForm<TicketActionResponse>(`/ops/tickets/${id}/${action}`, data);
}

// ==================== Metrics (Dashboard KPIs) ====================

/**
 * GET /api/metrics/summary - KPIs summary for dashboard
 */
export async function getMetricsSummary(
    params: MetricsParams = {}
): Promise<MetricsSummaryResponse> {
    if (USE_MOCKS) {
        const { getMetricsSummary: mockGetMetricsSummary } = await import('./api.mock.ts');
        return mockGetMetricsSummary(params);
    }

    const queryParams = new URLSearchParams();
    if (params.from) queryParams.set('from', params.from);
    if (params.to) queryParams.set('to', params.to);
    if (params.period) queryParams.set('period', params.period);
    if (params.area) queryParams.set('area', params.area);
    if (params.prioridad) queryParams.set('prioridad', params.prioridad);
    if (params.estado) queryParams.set('estado', params.estado);
    if (params.q) queryParams.set('q', params.q);

    const query = queryParams.toString();
    const endpoint = `/api/metrics/summary${query ? `?${query}` : ''}`;

    return get<MetricsSummaryResponse>(endpoint);
}

/**
 * GET /api/metrics/quality - Quality breakdown KPIs for dashboard
 */
export async function getMetricsQuality(
    params: MetricsParams = {}
): Promise<MetricsQualityResponse> {
    if (USE_MOCKS) {
        const { getMetricsQuality: mockGetMetricsQuality } = await import('./api.mock.ts');
        return mockGetMetricsQuality(params);
    }

    const queryParams = new URLSearchParams();
    if (params.from) queryParams.set('from', params.from);
    if (params.to) queryParams.set('to', params.to);
    if (params.period) queryParams.set('period', params.period);
    if (params.area) queryParams.set('area', params.area);
    if (params.prioridad) queryParams.set('prioridad', params.prioridad);
    if (params.estado) queryParams.set('estado', params.estado);
    if (params.q) queryParams.set('q', params.q);

    const query = queryParams.toString();
    const endpoint = `/api/metrics/quality${query ? `?${query}` : ''}`;

    return get<MetricsQualityResponse>(endpoint);
}
