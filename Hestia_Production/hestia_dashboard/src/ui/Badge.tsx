import type { TicketEstado, TicketPrioridad } from '../types/api';
import './Badge.css';

export type BadgeType = 'estado' | 'prioridad' | 'sla';
export type BadgeValue = TicketEstado | TicketPrioridad | 'overdue' | 'at-risk';

export interface BadgeProps {
    type: BadgeType;
    value: BadgeValue;
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
