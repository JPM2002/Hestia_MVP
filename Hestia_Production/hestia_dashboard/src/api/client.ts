// Centralized API client with environment-based configuration
// Handles fetch requests, error parsing, and credential management

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

export interface APIError {
    status: number;
    message: string;
    type: 'auth' | 'forbidden' | 'server' | 'network' | 'unknown';
}

export class APIClientError extends Error {
    readonly status: number;
    readonly type: APIError['type'];

    constructor(status: number, type: APIError['type'], message: string) {
        super(message);
        this.name = 'APIClientError';
        this.status = status;
        this.type = type;
    }
}

/**
 * Safe JSON parse - returns text if not valid JSON
 */
async function safeJsonParse(response: Response): Promise<any> {
    const text = await response.text();
    if (!text) return null;

    try {
        return JSON.parse(text);
    } catch {
        return text;
    }
}

/**
 * Core request method with error handling
 */
export async function request<T = unknown>(
    path: string,
    options: RequestInit = {}
): Promise<T> {
    const url = USE_MOCKS ? path : `${BASE_URL}${path}`;

    try {
        const response = await fetch(url, {
            ...options,
            credentials: 'include', // Always send cookies for session auth
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });

        // Handle error responses
        if (!response.ok) {
            const data = await safeJsonParse(response);
            const message = typeof data === 'object' && data?.error
                ? data.error
                : `HTTP ${response.status}: ${response.statusText}`;

            // Categorize errors
            if (response.status === 401) {
                throw new APIClientError(401, 'auth', message || 'No autenticado');
            } else if (response.status === 403) {
                throw new APIClientError(403, 'forbidden', message || 'Sin permisos');
            } else if (response.status >= 500) {
                throw new APIClientError(response.status, 'server', message || 'Error del servidor');
            } else {
                throw new APIClientError(response.status, 'unknown', message);
            }
        }

        // Parse successful response
        return await safeJsonParse(response);
    } catch (error) {
        // Network errors
        if (error instanceof APIClientError) {
            throw error;
        }

        throw new APIClientError(0, 'network', 'Error de conexión');
    }
}

/**
 * GET request helper
 */
export async function get<T = unknown>(
    path: string,
    options?: Omit<RequestInit, 'method' | 'body'>
): Promise<T> {
    return request<T>(path, { ...options, method: 'GET' });
}

/**
 * POST request helper with JSON body
 */
export async function post<T = unknown>(
    path: string,
    data?: unknown,
    options?: Omit<RequestInit, 'method' | 'body'>
): Promise<T> {
    return request<T>(path, {
        ...options,
        method: 'POST',
        body: data ? JSON.stringify(data) : undefined,
    });
}

/**
 * POST with form-urlencoded data (for legacy endpoints)
 */
export async function postForm<T = unknown>(
    path: string,
    data: Record<string, string> = {},
    options?: Omit<RequestInit, 'method' | 'body' | 'headers'>
): Promise<T> {
    const formData = new URLSearchParams(data);

    return request<T>(path, {
        ...options,
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
    });
}

/**
 * Special handling for login (handles redirects)
 */
export async function loginRequest(
    email: string,
    password: string
): Promise<{ ok: boolean }> {
    const url = USE_MOCKS ? '/auth/login' : `${BASE_URL}/auth/login`;
    const formData = new URLSearchParams({ email, password });

    try {
        const response = await fetch(url, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData.toString(),
            redirect: 'manual', // Don't follow redirects
        });

        // Opaque redirect or 302 = success
        if (
            response.type === 'opaqueredirect' ||
            response.status === 0 ||
            response.status === 302 ||
            response.ok
        ) {
            return { ok: true };
        }

        throw new APIClientError(response.status, 'auth', 'Credenciales inválidas');
    } catch (error) {
        if (error instanceof APIClientError) throw error;
        throw new APIClientError(0, 'network', 'Error de conexión');
    }
}

/**
 * Logout request
 */
export async function logoutRequest(): Promise<void> {
    const url = USE_MOCKS ? '/auth/logout' : `${BASE_URL}/auth/logout`;

    await fetch(url, {
        credentials: 'include',
        redirect: 'manual',
    });
}
