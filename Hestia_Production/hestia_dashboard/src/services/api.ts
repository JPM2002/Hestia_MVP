import type {
    MeResponse,
    TicketsListParams,
    TicketsListResponse,
    TicketDetailResponse,
    TicketEventsResponse,
    TicketActionResponse,
    TicketActionType,
} from '../types/api';

// Environment variables (Vite)
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

/**
 * Base fetch wrapper with cookie credentials support
 */
async function apiFetch<T>(
    endpoint: string,
    options: RequestInit = {}
): Promise<T> {
    const url = USE_MOCKS ? endpoint : `${API_BASE_URL}${endpoint}`;

    const response = await fetch(url, {
        ...options,
        credentials: 'include', // Send cookies for session auth
        headers: {
            ...options.headers,
        },
    });

    // Handle non-OK responses
    if (!response.ok) {
        if (response.status === 401) {
            // Unauthorized - redirect to login
            window.location.href = '/login';
            throw new Error('No autenticado');
        }

        // Try to parse error message from JSON
        try {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        } catch {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
    }

    // Parse JSON response
    return response.json();
}

/**
 * POST with form data (backend expects application/x-www-form-urlencoded)
 */
async function apiPostForm<T>(
    endpoint: string,
    data: Record<string, string> = {}
): Promise<T> {
    const formData = new URLSearchParams(data);

    return apiFetch<T>(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
    });
}

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

    const formData = new URLSearchParams({ email, password });

    try {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData.toString(),
            redirect: 'manual', // Don't follow redirects (may return opaqueredirect)
        });

        // Status 0 = opaque redirect (CORS redirect, considered success)
        // Status 302 = manual redirect
        // Status 200 = direct success
        if (response.type === 'opaqueredirect' || response.status === 0 || response.status === 302 || response.ok) {
            return { ok: true };
        }

        // Any other status = failure
        throw new Error('Credenciales inválidas');
    } catch (error) {
        if (error instanceof Error && error.message === 'Credenciales inválidas') {
            throw error;
        }
        // Network or other fetch errors
        throw new Error('Error de conexión');
    }
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

    await fetch(`${API_BASE_URL}/auth/logout`, {
        credentials: 'include',
        redirect: 'manual',
    });
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
    return apiFetch<MeResponse>('/api/me');
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

    return apiFetch<TicketsListResponse>(endpoint);
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
    return apiFetch<TicketDetailResponse>(`/api/tickets/${id}`);
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
    return apiFetch<TicketEventsResponse>(`/api/tickets/${id}/events`);
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

    return apiPostForm<TicketActionResponse>(`/ops/tickets/${id}/${action}`, data);
}
