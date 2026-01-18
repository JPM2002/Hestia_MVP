import type { Ticket } from '../types/api';

// Mock user names lookup
const MOCK_USERS: Record<number, string> = {
    1: 'Recepción',
    2: 'Supervisor',
    5: 'Juan Técnico',
    6: 'Carlos Técnico',
    7: 'Ana Roomservice',
    8: 'María Housekeeping',
};

/**
 * Format ISO date string to "dd/mm/yyyy HH:mm"
 */
export function formatDate(dateString: string | null): string {
    if (!dateString) return '-';
    const date = new Date(dateString);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${day}/${month}/${year} ${hours}:${minutes}`;
}

/**
 * Format ISO date string to "dd/mm/yyyy"
 */
export function formatDateShort(dateString: string | null): string {
    if (!dateString) return '-';
    const date = new Date(dateString);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    return `${day}/${month}/${year}`;
}

/**
 * Get user name from ID
 */
export function getUserName(userId: number | null | undefined): string {
    if (!userId) return 'Sin asignar';
    return MOCK_USERS[userId] || `Usuario #${userId}`;
}

/**
 * Calculate SLA status for a ticket
 */
export function getSLAStatus(ticket: Ticket): 'overdue' | 'at-risk' | null {
    // Only for open tickets
    if (ticket.estado === 'RESUELTO' || ticket.estado === 'ELIMINADO') {
        return null;
    }

    if (!ticket.due_at) return null;

    const now = new Date();
    const dueDate = new Date(ticket.due_at);
    const oneHourFromNow = new Date(now.getTime() + 60 * 60 * 1000);

    if (dueDate < now) {
        return 'overdue';
    }

    if (dueDate <= oneHourFromNow) {
        return 'at-risk';
    }

    return null;
}
