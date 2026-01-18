import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTicketById, getTicketEvents, updateTicketState } from '../services/api';
import type { Ticket, TicketEvent, TicketActionType } from '../types/api';
import { Badge } from '../components/Badge';
import { Modal } from '../components/Modal';
import { formatDate, getUserName, getSLAStatus } from '../utils/formatters';
import './TicketDetailPage.css';

export function TicketDetailPage() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const ticketId = parseInt(id || '0', 10);

    const [ticket, setTicket] = useState<Ticket | null>(null);
    const [events, setEvents] = useState<TicketEvent[]>([]);
    const [isLoadingTicket, setIsLoadingTicket] = useState(true);
    const [isLoadingEvents, setIsLoadingEvents] = useState(true);
    const [errorTicket, setErrorTicket] = useState<string | null>(null);
    const [errorEvents, setErrorEvents] = useState<string | null>(null);

    const [isProcessing, setIsProcessing] = useState(false);
    const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    const [showPauseModal, setShowPauseModal] = useState(false);

    // Load ticket and events
    const loadTicket = async () => {
        setIsLoadingTicket(true);
        setErrorTicket(null);
        try {
            const response = await getTicketById(ticketId);
            if (response.ok && response.ticket) {
                setTicket(response.ticket);
            } else {
                setErrorTicket(response.error || 'Ticket no encontrado');
            }
        } catch (err) {
            setErrorTicket(err instanceof Error ? err.message : 'Error al cargar ticket');
        } finally {
            setIsLoadingTicket(false);
        }
    };

    const loadEvents = async () => {
        setIsLoadingEvents(true);
        setErrorEvents(null);
        try {
            const response = await getTicketEvents(ticketId);
            if (response.ok && response.events) {
                // Sort by timestamp ascending
                const sorted = [...response.events].sort((a, b) => {
                    return new Date(a.at).getTime() - new Date(b.at).getTime();
                });
                setEvents(sorted);
            } else {
                setErrorEvents(response.error || 'Error al cargar eventos');
            }
        } catch (err) {
            setErrorEvents(err instanceof Error ? err.message : 'Error al cargar eventos');
        } finally {
            setIsLoadingEvents(false);
        }
    };

    useEffect(() => {
        loadTicket();
        loadEvents();
    }, [ticketId]);

    // Handle actions
    const handleAction = async (action: TicketActionType, motivo?: string) => {
        if (!ticket) return;

        setIsProcessing(true);
        setActionMessage(null);

        try {
            const response = await updateTicketState(ticketId, action, motivo);
            if (response.ok) {
                setActionMessage({ type: 'success', text: response.message || 'Acción completada' });
                // Refresh ticket and events
                await loadTicket();
                await loadEvents();
            } else {
                setActionMessage({ type: 'error', text: response.error || 'Error al ejecutar acción' });
            }
        } catch (err) {
            setActionMessage({ type: 'error', text: err instanceof Error ? err.message : 'Error al ejecutar acción' });
        } finally {
            setIsProcessing(false);
            // Auto-hide message after 5 seconds
            setTimeout(() => setActionMessage(null), 5000);
        }
    };

    const handlePauseClick = () => {
        setShowPauseModal(true);
    };

    const handlePauseConfirm = (motivo: string) => {
        setShowPauseModal(false);
        handleAction('pause', motivo);
    };

    // Determine available actions based on current estado
    const getAvailableActions = (): TicketActionType[] => {
        if (!ticket) return [];

        const { estado } = ticket;

        if (['PENDIENTE', 'ASIGNADO', 'DERIVADO'].includes(estado)) {
            return ['accept'];
        }
        if (estado === 'ACEPTADO') {
            return ['start'];
        }
        if (estado === 'EN_CURSO') {
            return ['pause', 'finish'];
        }
        if (estado === 'PAUSADO') {
            return ['resume'];
        }

        return [];
    };

    const availableActions = getAvailableActions();
    const slaStatus = ticket ? getSLAStatus(ticket) : null;

    return (
        <div className="ticketDetailPage">
            {/* Header with Back Button */}
            <div className="detailHeader">
                <button className="btnBack" onClick={() => navigate('/tickets')}>
                    ← Volver
                </button>
                <h1>Ticket #{ticketId}</h1>
            </div>

            {/* Action Message */}
            {actionMessage && (
                <div className={`actionMessage ${actionMessage.type}`}>
                    {actionMessage.text}
                </div>
            )}

            {/* Ticket Info */}
            {isLoadingTicket && (
                <div className="stateMessage">
                    <p>Cargando ticket...</p>
                </div>
            )}

            {!isLoadingTicket && errorTicket && (
                <div className="stateMessage stateError">
                    <p>{errorTicket}</p>
                    <button className="btnRetry" onClick={loadTicket}>
                        Reintentar
                    </button>
                </div>
            )}

            {!isLoadingTicket && !errorTicket && ticket && (
                <div className="ticketInfo">
                    <div className="infoCard">
                        <div className="infoHeader">
                            <h2>{ticket.ubicacion || 'Sin ubicación'}</h2>
                            <div className="badges">
                                <Badge type="estado" value={ticket.estado} />
                                <Badge type="prioridad" value={ticket.prioridad} />
                                {slaStatus && <Badge type="sla" value={slaStatus} />}
                            </div>
                        </div>

                        <div className="infoGrid">
                            <div className="infoItem">
                                <span className="infoLabel">Área:</span>
                                <span className="infoValue">{ticket.area}</span>
                            </div>
                            <div className="infoItem">
                                <span className="infoLabel">Asignado:</span>
                                <span className="infoValue">{getUserName(ticket.assigned_to)}</span>
                            </div>
                            <div className="infoItem">
                                <span className="infoLabel">Creado:</span>
                                <span className="infoValue">{formatDate(ticket.created_at)}</span>
                            </div>
                            <div className="infoItem">
                                <span className="infoLabel">Vencimiento:</span>
                                <span className="infoValue">{formatDate(ticket.due_at)}</span>
                            </div>
                            {ticket.finished_at && (
                                <div className="infoItem">
                                    <span className="infoLabel">Finalizado:</span>
                                    <span className="infoValue">{formatDate(ticket.finished_at)}</span>
                                </div>
                            )}
                        </div>

                        <div className="infoDescription">
                            <h3>Descripción</h3>
                            <p>{ticket.detalle}</p>
                        </div>

                        {/* Action Buttons */}
                        {availableActions.length > 0 && (
                            <div className="actionButtons">
                                {availableActions.includes('accept') && (
                                    <button
                                        className="btnAction btnAccept"
                                        onClick={() => handleAction('accept')}
                                        disabled={isProcessing}
                                    >
                                        Aceptar
                                    </button>
                                )}
                                {availableActions.includes('start') && (
                                    <button
                                        className="btnAction btnStart"
                                        onClick={() => handleAction('start')}
                                        disabled={isProcessing}
                                    >
                                        Iniciar
                                    </button>
                                )}
                                {availableActions.includes('pause') && (
                                    <button
                                        className="btnAction btnPause"
                                        onClick={handlePauseClick}
                                        disabled={isProcessing}
                                    >
                                        Pausar
                                    </button>
                                )}
                                {availableActions.includes('resume') && (
                                    <button
                                        className="btnAction btnResume"
                                        onClick={() => handleAction('resume')}
                                        disabled={isProcessing}
                                    >
                                        Reanudar
                                    </button>
                                )}
                                {availableActions.includes('finish') && (
                                    <button
                                        className="btnAction btnFinish"
                                        onClick={() => handleAction('finish')}
                                        disabled={isProcessing}
                                    >
                                        Finalizar
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Timeline */}
            <div className="timelineSection">
                <h2>Timeline</h2>

                {isLoadingEvents && (
                    <div className="stateMessage">
                        <p>Cargando eventos...</p>
                    </div>
                )}

                {!isLoadingEvents && errorEvents && (
                    <div className="stateMessage stateError">
                        <p>{errorEvents}</p>
                        <button className="btnRetry" onClick={loadEvents}>
                            Reintentar
                        </button>
                    </div>
                )}

                {!isLoadingEvents && !errorEvents && events.length === 0 && (
                    <div className="stateMessage">
                        <p>Sin eventos registrados</p>
                    </div>
                )}

                {!isLoadingEvents && !errorEvents && events.length > 0 && (
                    <div className="timeline">
                        {events.map((event) => (
                            <div key={event.id || event.at} className="timelineEvent">
                                <div className="eventDot"></div>
                                <div className="eventContent">
                                    <div className="eventAction">{event.action}</div>
                                    <div className="eventMeta">
                                        <span className="eventActor">{event.actor}</span>
                                        <span className="eventTime">{formatDate(event.at)}</span>
                                    </div>
                                    {event.motivo && <div className="eventMotivo">Motivo: {event.motivo}</div>}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Pause Modal */}
            <Modal
                isOpen={showPauseModal}
                title="Pausar Ticket"
                onClose={() => setShowPauseModal(false)}
                onConfirm={handlePauseConfirm}
                placeholder="Ingrese el motivo de la pausa..."
            />
        </div>
    );
}
