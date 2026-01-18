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

    // Filter states
    const [filterEstado, setFilterEstado] = useState<TicketEstado | ''>('');
    const [filterPrioridad, setFilterPrioridad] = useState<TicketPrioridad | ''>('');
    const [filterArea, setFilterArea] = useState<TicketArea | ''>('');
    const [filterAsignado, setFilterAsignado] = useState<string>('');
    const [filterFrom, setFilterFrom] = useState('');
    const [filterTo, setFilterTo] = useState('');
    const [filterSearch, setFilterSearch] = useState('');

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

    // Client-side filtering
    const filteredTickets = useMemo(() => {
        let filtered = [...tickets];

        if (filterEstado) {
            filtered = filtered.filter((t) => t.estado === filterEstado);
        }

        if (filterPrioridad) {
            filtered = filtered.filter((t) => t.prioridad === filterPrioridad);
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

        return filtered;
    }, [tickets, filterEstado, filterPrioridad, filterArea, filterAsignado, filterFrom, filterTo, filterSearch]);

    const clearFilters = () => {
        setFilterEstado('');
        setFilterPrioridad('');
        setFilterArea('');
        setFilterAsignado('');
        setFilterFrom('');
        setFilterTo('');
        setFilterSearch('');
    };

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
                    <select value={filterEstado} onChange={(e) => setFilterEstado(e.target.value as TicketEstado | '')}>
                        <option value="">Todos</option>
                        <option value="PENDIENTE">Pendiente</option>
                        <option value="ASIGNADO">Asignado</option>
                        <option value="ACEPTADO">Aceptado</option>
                        <option value="EN_CURSO">En Curso</option>
                        <option value="PAUSADO">Pausado</option>
                        <option value="RESUELTO">Resuelto</option>
                    </select>
                </div>

                <div className="filterGroup">
                    <label>Prioridad:</label>
                    <select value={filterPrioridad} onChange={(e) => setFilterPrioridad(e.target.value as TicketPrioridad | '')}>
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
                    <input type="date" value={filterFrom} onChange={(e) => setFilterFrom(e.target.value)} />
                </div>

                <div className="filterGroup">
                    <label>Hasta:</label>
                    <input type="date" value={filterTo} onChange={(e) => setFilterTo(e.target.value)} />
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
                                        <tr key={ticket.id} onClick={() => handleRowClick(ticket.id)} className="clickableRow">
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
                                            <td>
                                                {slaStatus && <Badge type="sla" value={slaStatus} />}
                                            </td>
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
