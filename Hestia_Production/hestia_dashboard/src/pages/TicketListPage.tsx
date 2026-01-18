import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getTickets } from '../services/api';
import type { Ticket, TicketEstado, TicketPrioridad, TicketArea } from '../types/api';
import { Badge } from '../components/Badge';
import { formatDateShort, getUserName, getSLAStatus } from '../utils/formatters';
import './TicketListPage.css';

export function TicketListPage() {
    const navigate = useNavigate();
    const [tickets, setTickets] = useState<Ticket[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // NEW: Critical toggle
    const [criticalOnly, setCriticalOnly] = useState(false);

    // Filter states
    const [filterEstado, setFilterEstado] = useState<TicketEstado | ''>('');
    const [filterPrioridad, setFilterPrioridad] = useState<TicketPrioridad | ''>('');
    const [filterArea, setFilterArea] = useState<TicketArea | ''>('');
    const [filterAsignado, setFilterAsignado] = useState<string>('');
    const [filterFrom, setFilterFrom] = useState('');
    const [filterTo, setFilterTo] = useState('');
    const [filterSearch, setFilterSearch] = useState('');

    // Helpers
    const getTodayInputValue = () => {
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const d = String(now.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`; // yyyy-mm-dd para input date
    };

    const isToday = (iso: string) => {
        const d = new Date(iso);
        const now = new Date();
        return (
            d.getFullYear() === now.getFullYear() &&
            d.getMonth() === now.getMonth() &&
            d.getDate() === now.getDate()
        );
    };

    // Load tickets
    const loadTickets = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await getTickets({});
            setTickets(response.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar tickets');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        loadTickets();
    }, []);

    const clearFilters = () => {
        setFilterEstado('');
        setFilterPrioridad('');
        setFilterArea('');
        setFilterAsignado('');
        setFilterFrom('');
        setFilterTo('');
        setFilterSearch('');
        setCriticalOnly(false);
    };

    // NEW: toggle críticos (setea filtros)
    const toggleCritical = () => {
        if (criticalOnly) {
            // OFF -> vuelve a vacío
            clearFilters();
            return;
        }

        // ON -> setea las 3 condiciones
        const today = getTodayInputValue();
        setCriticalOnly(true);

        // 1) Pendientes
        setFilterEstado('PENDIENTE');

        // 2) Alta prioridad (incluiremos URGENTE en el filtrado)
        setFilterPrioridad('ALTA');

        // 3) Hoy
        setFilterFrom(today);
        setFilterTo(today);

        // opcional: limpiar otros filtros para que sea “rápido y claro”
        setFilterArea('');
        setFilterAsignado('');
        setFilterSearch('');
    };

    // Client-side filtering
    const filteredTickets = useMemo(() => {
        let filtered = [...tickets];

        // Estado: si eligen "PENDIENTE", incluir también PENDIENTE_APROBACION
        if (filterEstado) {
            if (filterEstado === 'PENDIENTE') {
                filtered = filtered.filter((t) =>
                    t.estado === 'PENDIENTE' || t.estado === 'PENDIENTE_APROBACION'
                );
            } else {
                filtered = filtered.filter((t) => t.estado === filterEstado);
            }
        }

        // Prioridad: si críticos está ON y prioridad=ALTA, incluir URGENTE también
        if (filterPrioridad) {
            if (criticalOnly && filterPrioridad === 'ALTA') {
                filtered = filtered.filter((t) => t.prioridad === 'ALTA' || t.prioridad === 'URGENTE');
            } else {
                filtered = filtered.filter((t) => t.prioridad === filterPrioridad);
            }
        }

        if (filterArea) {
            filtered = filtered.filter((t) => t.area === filterArea);
        }

        if (filterAsignado) {
            if (filterAsignado === 'unassigned') {
                filtered = filtered.filter((t) => !t.assigned_to);
            } else {
                const userId = parseInt(filterAsignado, 10);
                filtered = filtered.filter((t) => t.assigned_to === userId);
            }
        }

        if (filterFrom) {
            const fromDate = new Date(`${filterFrom}T00:00:00`);
            filtered = filtered.filter((t) => new Date(t.created_at) >= fromDate);
        }

        if (filterTo) {
            const toDate = new Date(`${filterTo}T23:59:59`);
            filtered = filtered.filter((t) => new Date(t.created_at) <= toDate);
        }

        if (filterSearch) {
            const search = filterSearch.toLowerCase();
            filtered = filtered.filter(
                (t) =>
                    (t.ubicacion || '').toLowerCase().includes(search) ||
                    (t.detalle || '').toLowerCase().includes(search)
            );
        }

        // Extra garantía: si críticos ON, forzar las 3 condiciones aunque alguien intente tocar algo
        if (criticalOnly) {
            filtered = filtered.filter((t) => {
                const pending = t.estado === 'PENDIENTE' || t.estado === 'PENDIENTE_APROBACION';
                const high = t.prioridad === 'ALTA' || t.prioridad === 'URGENTE';
                const today = isToday(t.created_at);
                return pending && high && today;
            });
        }

        return filtered;
    }, [
        tickets,
        filterEstado,
        filterPrioridad,
        filterArea,
        filterAsignado,
        filterFrom,
        filterTo,
        filterSearch,
        criticalOnly,
    ]);

    const handleRowClick = (id: number) => {
        navigate(`/tickets/${id}`);
    };

    return (
        <div className="ticketsPage">
            <div className="pageHeader">
                <h1>Tickets</h1>
                <p>Gestión de tickets de soporte</p>
            </div>

            {/* Filters */}
            <div className="filtersBar">
                <div className="filterGroup">
                    <label>Estado:</label>
                    <select
                        value={filterEstado}
                        disabled={criticalOnly}
                        onChange={(e) => setFilterEstado(e.target.value as TicketEstado | '')}
                    >
                        <option value="">Todos</option>
                        <option value="PENDIENTE">Pendiente</option>
                        <option value="PENDIENTE_APROBACION">Pend. Aprobación</option>
                        <option value="ASIGNADO">Asignado</option>
                        <option value="ACEPTADO">Aceptado</option>
                        <option value="EN_CURSO">En Curso</option>
                        <option value="PAUSADO">Pausado</option>
                        <option value="RESUELTO">Resuelto</option>
                    </select>
                </div>

                <div className="filterGroup">
                    <label>Prioridad:</label>
                    <select
                        value={filterPrioridad}
                        disabled={criticalOnly}
                        onChange={(e) => setFilterPrioridad(e.target.value as TicketPrioridad | '')}
                    >
                        <option value="">Todas</option>
                        <option value="BAJA">Baja</option>
                        <option value="MEDIA">Media</option>
                        <option value="ALTA">Alta</option>
                        <option value="URGENTE">Urgente</option>
                    </select>
                </div>

                <div className="filterGroup">
                    <label>Área:</label>
                    <select value={filterArea} onChange={(e) => setFilterArea(e.target.value as TicketArea | '')}>
                        <option value="">Todas</option>
                        <option value="MANTENCION">Mantención</option>
                        <option value="HOUSEKEEPING">Housekeeping</option>
                        <option value="ROOMSERVICE">Room Service</option>
                    </select>
                </div>

                <div className="filterGroup">
                    <label>Asignado:</label>
                    <select value={filterAsignado} onChange={(e) => setFilterAsignado(e.target.value)}>
                        <option value="">Todos</option>
                        <option value="unassigned">Sin asignar</option>
                        <option value="5">Juan Técnico</option>
                        <option value="6">Carlos Técnico</option>
                        <option value="7">Ana Roomservice</option>
                        <option value="8">María Housekeeping</option>
                    </select>
                </div>

                <div className="filterGroup">
                    <label>Desde:</label>
                    <input
                        type="date"
                        value={filterFrom}
                        disabled={criticalOnly}
                        onChange={(e) => setFilterFrom(e.target.value)}
                    />
                </div>

                <div className="filterGroup">
                    <label>Hasta:</label>
                    <input
                        type="date"
                        value={filterTo}
                        disabled={criticalOnly}
                        onChange={(e) => setFilterTo(e.target.value)}
                    />
                </div>

                <div className="filterGroup filterGroupWide">
                    <label>Buscar:</label>
                    <input
                        type="text"
                        placeholder="Habitación o palabra clave..."
                        value={filterSearch}
                        onChange={(e) => setFilterSearch(e.target.value)}
                    />
                </div>

                {/* NEW: Critical button */}
                <button
                    type="button"
                    className={`btnCritical ${criticalOnly ? 'active' : ''}`}
                    onClick={toggleCritical}
                    title="Pendiente + Alta/Urgente + Hoy"
                >
                    CRITICOS
                </button>

                <button className="btnClearFilters" onClick={clearFilters}>
                    Limpiar filtros
                </button>
            </div>

            {/* Content */}
            <div className="tableCard">
                {isLoading && (
                    <div className="stateMessage">
                        <p>Cargando tickets...</p>
                    </div>
                )}

                {!isLoading && error && (
                    <div className="stateMessage stateError">
                        <p>{error}</p>
                        <button className="btnRetry" onClick={loadTickets}>
                            Reintentar
                        </button>
                    </div>
                )}

                {!isLoading && !error && filteredTickets.length === 0 && (
                    <div className="stateMessage">
                        <p>No se encontraron tickets</p>
                    </div>
                )}

                {!isLoading && !error && filteredTickets.length > 0 && (
                    <div className="tableWrapper">
                        <table className="ticketsTable">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Estado</th>
                                    <th>Prioridad</th>
                                    <th>Habitación</th>
                                    <th>Área</th>
                                    <th>Asignado</th>
                                    <th>Creado</th>
                                    <th>SLA</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredTickets.map((ticket) => {
                                    const slaStatus = getSLAStatus(ticket);
                                    return (
                                        <tr
                                            key={ticket.id}
                                            onClick={() => handleRowClick(ticket.id)}
                                            className="clickableRow"
                                        >
                                            <td className="mono">#{ticket.id}</td>
                                            <td>
                                                <Badge type="estado" value={ticket.estado} />
                                            </td>
                                            <td>
                                                <Badge type="prioridad" value={ticket.prioridad} />
                                            </td>
                                            <td>{ticket.ubicacion || '-'}</td>
                                            <td>{ticket.area}</td>
                                            <td>{getUserName(ticket.assigned_to)}</td>
                                            <td>{formatDateShort(ticket.created_at)}</td>
                                            <td>{slaStatus && <Badge type="sla" value={slaStatus} />}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
