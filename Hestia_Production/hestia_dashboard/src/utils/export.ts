import type { Ticket } from '../types/api';

/**
 * Export array of tickets to CSV format
 */
export function exportToCSV(tickets: Ticket[], filename: string = 'tickets.csv'): void {
    if (!tickets || tickets.length === 0) {
        console.warn('No tickets to export');
        return;
    }

    // CSV Headers
    const headers = ['ID', 'Estado', 'Prioridad', 'Área', 'Habitación', 'Detalle', 'Asignado', 'Creado', 'Vencimiento'];

    // Escape CSV value (handle commas and quotes)
    const escapeCSV = (value: unknown): string => {
        if (value === null || value === undefined) return '';
        const str = String(value);
        // If contains comma, quote, or newline, wrap in quotes and escape internal quotes
        if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
    };

    // Build CSV rows
    const rows = tickets.map(ticket => [
        ticket.id,
        ticket.estado,
        ticket.prioridad,
        ticket.area,
        ticket.ubicacion || '',
        ticket.detalle || '',
        ticket.assigned_to || 'Sin asignar',
        ticket.created_at,
        ticket.due_at || '',
    ]);

    // Combine headers and rows
    const csvContent = [
        headers.map(escapeCSV).join(','),
        ...rows.map(row => row.map(escapeCSV).join(','))
    ].join('\n');

    // Create and download blob
    downloadBlob(csvContent, filename, 'text/csv;charset=utf-8;');
}

/**
 * Export array of tickets to JSON format
 */
export function exportToJSON(tickets: Ticket[], filename: string = 'tickets.json'): void {
    if (!tickets || tickets.length === 0) {
        console.warn('No tickets to export');
        return;
    }

    // Pretty-print JSON
    const jsonContent = JSON.stringify(tickets, null, 2);

    // Create and download blob
    downloadBlob(jsonContent, filename, 'application/json;charset=utf-8;');
}

/**
 * Helper to download blob as file
 */
function downloadBlob(content: string, filename: string, mimeType: string): void {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);

    // Create temporary link and trigger download
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';

    document.body.appendChild(link);
    link.click();

    // Cleanup
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}
