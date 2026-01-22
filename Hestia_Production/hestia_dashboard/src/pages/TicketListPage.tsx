import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getTickets } from '../services/api';
import type { Ticket, TicketEstado, TicketPrioridad, TicketArea } from '../types/api';
import { Badge } from '../components/Badge';
import { formatDateShort, getUserName, getSLAStatus } from '../utils/formatters';
import { exportToCSV, exportToJSON } from '../utils/export';
import { Card } from '../ui/Card';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import './TicketListPage.css';

const PAGE_SIZE = 20;

export function TicketListPage() {
    const navigate = useNavigate();
    const [tickets, setTickets] = useState<Ticket[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Pagination
    const [currentPage, setCurrentPage] = useState(1);

    // Auto-refresh
    const [autoRefresh, setAutoRefresh] = useState(false);

    // Critical toggle
    const [criticalOnly, setCriticalOnly] = useState(false);

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

    // Auto-refresh effect
    useEffect(() => {
        if (!autoRefresh) return;

        const interval = setInterval(() => {
            loadTickets();
        }, 45000); // 45 seconds

        return () => clearInterval(interval);
    }, [autoRefresh]);

    const clearFilters = () => {
        setFilterEstado('');
        setFilterPrioridad('');
        setFilterArea('');
        setFilterAsignado('');
        setFilterFrom('');
        setFilterTo('');
        setFilterSearch('');
        setCriticalOnly(false);
        setCurrentPage(1);
    };

    // Toggle críticos (setea filtros)
    const toggleCritical = () => {
        if (criticalOnly) {
            // OFF -> vuelve a vacío
            clearFilters();
            return;
        }

        // ON -> setea solo 2 condiciones: estado + prioridad
        setCriticalOnly(true);
        setFilterEstado('PENDIENTE');
        setFilterPrioridad('ALTA');
        setFilterArea('');
        setFilterAsignado('');
        setFilterSearch('');
        setFilterFrom('');
        setFilterTo('');
        setCurrentPage(1);
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

        // Date filters: only apply if NOT in critical mode
        if (!criticalOnly && filterFrom) {
            const fromDate = new Date(`${filterFrom}T00:00:00`);
            filtered = filtered.filter((t) => new Date(t.created_at) >= fromDate);
        }

        if (!criticalOnly && filterTo) {
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

        // Extra garantía: si críticos ON, forzar las 2 condiciones (estado + prioridad)
        if (criticalOnly) {
            filtered = filtered.filter((t) => {
                const pending = t.estado === 'PENDIENTE' || t.estado === 'PENDIENTE_APROBACION';
                const high = t.prioridad === 'ALTA' || t.prioridad === 'URGENTE';
                return pending && high;
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

    // Pagination
    const totalPages = Math.ceil(filteredTickets.length / PAGE_SIZE);
    const paginatedTickets = useMemo(() => {
        const start = (currentPage - 1) * PAGE_SIZE;
        return filteredTickets.slice(start, start + PAGE_SIZE);
    }, [filteredTickets, currentPage]);

    // Reset page when filters change
    useEffect(() => {
        setCurrentPage(1);
    }, [filterEstado, filterPrioridad, filterArea, filterAsignado, filterFrom, filterTo, filterSearch, criticalOnly]);

    const handleRowClick = (id: number) => {
        navigate(`/tickets/${id}`);
    };

    const handleExportCSV = () => {
        exportToCSV(filteredTickets, `tickets_${new Date().toISOString().split('T')[0]}.csv`);
    };

    const handleExportJSON = () => {
        exportToJSON(filteredTickets, `tickets_${new Date().toISOString().split('T')[0]}.json`);
    };

    const estadoOptions = [
        { value: '', label: 'Todos' },
        { value: 'PENDIENTE', label: 'Pendiente' },
        { value: 'PENDIENTE_APROBACION', label: 'Pend. Aprobación' },
        { value: 'ASIGNADO', label: 'Asignado' },
        { value: 'ACEPTADO', label: 'Aceptado' },
        { value: 'EN_CURSO', label: 'En Curso' },
        { value: 'PAUSADO', label: 'Pausado' },
        { value: 'RESUELTO', label: 'Resuelto' },
    ];

    const prioridadOptions = [
        { value: '', label: 'Todas' },
        { value: 'BAJA', label: 'Baja' },
        { value: 'MEDIA', label: 'Media' },
        { value: 'ALTA', label: 'Alta' },
        { value: 'URGENTE', label: 'Urgente' },
    ];

    const areaOptions = [
        { value: '', label: 'Todas' },
        { value: 'MANTENCION', label: 'Mantención' },
        { value: 'HOUSEKEEPING', label: 'Housekeeping' },
        { value: 'ROOMSERVICE', label: 'Room Service' },
    ];

    const asignadoOptions = [
        { value: '', label: 'Todos' },
        { value: 'unassigned', label: 'Sin asignar' },
        { value: '5', label: 'Juan Técnico' },
        { value: '6', label: 'Carlos Técnico' },
        { value: '7', label: 'Ana Roomservice' },
        { value: '8', label: 'María Housekeeping' },
    ];

    return (
        <div className="ticketsPage">
            <div className="pageHeader">
                <h1>Tickets</h1>
                <p>Gestión de tickets de soporte</p>
            </div>

            {/* Filters */}
            <Card className="filtersCard">
                <div className="filtersBar">
                    <Select
                        label="Estado:"
                        value={filterEstado}
                        onChange={(e) => setFilterEstado(e.target.value as TicketEstado | '')}
                        options={estadoOptions}
                        disabled={criticalOnly}
                    />

                    <Select
                        label="Prioridad:"
                        value={filterPrioridad}
                        onChange={(e) => setFilterPrioridad(e.target.value as TicketPrioridad | '')}
                        options={prioridadOptions}
                        disabled={criticalOnly}
                    />

                    <Select
                        label="Área:"
                        value={filterArea}
                        onChange={(e) => setFilterArea(e.target.value as TicketArea | '')}
                        options={areaOptions}
                    />

                    <Select
                        label="Asignado:"
                        value={filterAsignado}
                        onChange={(e) => setFilterAsignado(e.target.value)}
                        options={asignadoOptions}
                    />

                    <Input
                        label="Desde:"
                        type="date"
                        value={filterFrom}
                        onChange={(e) => setFilterFrom(e.target.value)}
                        disabled={criticalOnly}
                    />

                    <Input
                        label="Hasta:"
                        type="date"
                        value={filterTo}
                        onChange={(e) => setFilterTo(e.target.value)}
                        disabled={criticalOnly}
                    />

                    <Input
                        label="Buscar:"
                        type="text"
                        placeholder="Habitación o palabra clave..."
                        value={filterSearch}
                        onChange={(e) => setFilterSearch(e.target.value)}
                    />
                </div>

                <div className="filtersActions">
                    <Button
                        variant={criticalOnly ? 'danger' : 'secondary'}
                        onClick={toggleCritical}
                    >
                        CRÍTICOS
                    </Button>

                    <Button variant="ghost" onClick={clearFilters}>
                        Limpiar filtros
                    </Button>

                    <div className="divider" />

                    <Button variant="secondary" onClick={loadTickets} disabled={isLoading}>
                        🔄 Actualizar
                    </Button>

                    <label className="autoRefreshLabel">
                        <input
                            type="checkbox"
                            checked={autoRefresh}
                            onChange={(e) => setAutoRefresh(e.target.checked)}
                        />
                        <span>Auto (45s)</span>
                    </label>

                    <div className="divider" />

                    <Button variant="ghost" onClick={handleExportCSV} disabled={filteredTickets.length === 0}>
                        📥 CSV
                    </Button>

                    <Button variant="ghost" onClick={handleExportJSON} disabled={filteredTickets.length === 0}>
                        📥 JSON
                    </Button>
                </div>
            </Card>

            {/* Content */}
            <Card className="tableCard">
                {isLoading && (
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
                                {[...Array(5)].map((_, i) => (
                                    <tr key={i}>
                                        <td><Skeleton width={60} /></td>
                                        <td><Skeleton width={80} /></td>
                                        <td><Skeleton width={70} /></td>
                                        <td><Skeleton width={50} /></td>
                                        <td><Skeleton width={100} /></td>
                                        <td><Skeleton width={120} /></td>
                                        <td><Skeleton width={90} /></td>
                                        <td><Skeleton width={70} /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {!isLoading && error && (
                    <div className="stateMessage stateError">
                        <p>{error}</p>
                        <Button variant="primary" onClick={loadTickets}>
                            Reintentar
                        </Button>
                    </div>
                )}

                {!isLoading && !error && filteredTickets.length === 0 && (
                    <div className="stateMessage">
                        <p>No se encontraron tickets</p>
                    </div>
                )}

                {!isLoading && !error && paginatedTickets.length > 0 && (
                    <>
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
                                    {paginatedTickets.map((ticket) => {
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

                        {/* Pagination */}
                        {totalPages > 1 && (
                            <div className="paginationBar">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                    disabled={currentPage === 1}
                                >
                                    ← Anterior
                                </Button>

                                <span className="paginationInfo">
                                    Página {currentPage} de {totalPages} ({filteredTickets.length} tickets)
                                </span>

                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                    disabled={currentPage === totalPages}
                                >
                                    Siguiente →
                                </Button>
                            </div>
                        )}
                    </>
                )}
            </Card>
        </div>
    );
}
