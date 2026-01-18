import type { TicketEstado, TicketPrioridad } from '../types/api';
import './Badge.css';

interface BadgeProps {
    type: 'estado' | 'prioridad' | 'sla';
    value: TicketEstado | TicketPrioridad | 'overdue' | 'at-risk';
    label?: string;
}

export function Badge({ type, value, label }: BadgeProps) {
    let className = 'badge';
    let displayText = label || value;

    if (type === 'estado') {
        className += ` badge-estado-${value.toLowerCase().replace('_', '-')}`;
    } else if (type === 'prioridad') {
        className += ` badge-prioridad-${value.toLowerCase()}`;
    } else if (type === 'sla') {
        className += ` badge-sla-${value}`;
        displayText = value === 'overdue' ? 'Vencido' : 'En riesgo';
    }

    return <span className={className}>{displayText}</span>;
}
