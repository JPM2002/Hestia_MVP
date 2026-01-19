import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMetricsSummary, getMetricsQuality, getTickets } from '../services/api';
import type {
    MetricsSummaryResponse,
    MetricsQualityResponse,
    MetricsPeriod,
    MetricsQualityRow,
    Ticket,
} from '../types/api';
import { Badge } from '../components/Badge';
import { getUserName, getSLAStatus, formatDateShort, formatDate } from '../utils/formatters';
import './MetricsPage.css';

type TabType = 'summary' | 'quality' | 'performance' | 'recurring';

interface WorkerPerformance {
    userId: number;
    userName: string;
    assignedOpen: number;
    inProgress: number;
    resolved30d: number;
    avgTTRMinutes: number;
    slaPercentage: number | null;
}

interface RecurringGroup {
    type: string;
    location: string;
    count: number;
    lastCreated: string;
    ticketIds: number[];
}

export function MetricsPage() {
    const navigate = useNavigate();
    const [activeTab, setActiveTab] = useState<TabType>('summary');
    const [period, setPeriod] = useState<MetricsPeriod>('7d');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Summary data
    const [summaryData, setSummaryData] = useState<MetricsSummaryResponse | null>(null);

    // Quality data
    const [qualityData, setQualityData] = useState<MetricsQualityResponse | null>(null);

    // Performance data
    const [allTickets, setAllTickets] = useState<Ticket[]>([]);
    const [selectedWorker, setSelectedWorker] = useState<number | null>(null);

    // Recurring data
    const [selectedRecurringGroup, setSelectedRecurringGroup] = useState<RecurringGroup | null>(null);

    // Fetch summary data
    const fetchSummary = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const data = await getMetricsSummary({ period });
            setSummaryData(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar resumen');
        } finally {
            setIsLoading(false);
        }
    };

    // Fetch quality data
    const fetchQuality = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const data = await getMetricsQuality({ period });
            setQualityData(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar calidad');
        } finally {
            setIsLoading(false);
        }
    };

    // Fetch all tickets for performance and recurring tabs
    const fetchAllTickets = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await getTickets({});
            setAllTickets(response.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar tickets');
        } finally {
            setIsLoading(false);
        }
    };

    // Load data when tab or period changes
    useEffect(() => {
        if (activeTab === 'summary') {
            fetchSummary();
        } else if (activeTab === 'quality') {
            fetchQuality();
        } else if (activeTab === 'performance' || activeTab === 'recurring') {
            fetchAllTickets();
        }
        // Reset drill-down states when changing tabs
        setSelectedWorker(null);
        setSelectedRecurringGroup(null);
    }, [activeTab, period]);

    // Calculate worker performance metrics
    const workerPerformance = useMemo(() => {
        const now = new Date();
        const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

        // Group tickets by assigned user
        const workerMap = new Map<number, Ticket[]>();
        allTickets.forEach((ticket) => {
            if (ticket.assigned_to) {
                if (!workerMap.has(ticket.assigned_to)) {
                    workerMap.set(ticket.assigned_to, []);
                }
                workerMap.get(ticket.assigned_to)!.push(ticket);
            }
        });

        const performance: WorkerPerformance[] = [];
        workerMap.forEach((tickets, userId) => {
            // Asignados abiertos: NOT RESUELTO/ELIMINADO
            const assignedOpen = tickets.filter(
                (t) => t.estado !== 'RESUELTO' && t.estado !== 'ELIMINADO'
            ).length;

            // En curso: estado EN_CURSO (incluimos ACEPTADO como "en proceso")
            const inProgress = tickets.filter(
                (t) => t.estado === 'EN_CURSO' || t.estado === 'ACEPTADO'
            ).length;

            // Resueltos (30d): con finished_at en últimos 30 días
            const resolved30d = tickets.filter((t) => {
                if (!t.finished_at) return false;
                const finishedDate = new Date(t.finished_at);
                return finishedDate >= thirtyDaysAgo;
            });

            // TTR promedio: minutos entre created_at y finished_at
            const ttrValues = resolved30d
                .filter((t) => t.finished_at) // solo los que tienen finished_at
                .map((t) => {
                    const created = new Date(t.created_at).getTime();
                    const finished = new Date(t.finished_at!).getTime();
                    return Math.max(0, Math.round((finished - created) / 60000));
                });

            const avgTTRMinutes =
                ttrValues.length > 0
                    ? Math.round(ttrValues.reduce((a, b) => a + b, 0) / ttrValues.length)
                    : 0;

            // SLA %: de los resueltos 30d con due_at, cuántos finished_at <= due_at
            const resolved30dWithDue = resolved30d.filter((t) => t.due_at);
            const slaOk = resolved30dWithDue.filter((t) => {
                const finished = new Date(t.finished_at!);
                const due = new Date(t.due_at!);
                return finished <= due;
            }).length;

            const slaPercentage =
                resolved30dWithDue.length > 0
                    ? Math.round((slaOk / resolved30dWithDue.length) * 1000) / 10
                    : null;

            performance.push({
                userId,
                userName: getUserName(userId),
                assignedOpen,
                inProgress,
                resolved30d: resolved30d.length,
                avgTTRMinutes,
                slaPercentage,
            });
        });

        // Sort by resolved30d desc, then inProgress desc
        return performance.sort((a, b) => {
            if (b.resolved30d !== a.resolved30d) return b.resolved30d - a.resolved30d;
            return b.inProgress - a.inProgress;
        });
    }, [allTickets]);

    // Get tickets for selected worker (sorted: open first, then resolved)
    const workerTickets = useMemo(() => {
        if (selectedWorker === null) return [];
        const tickets = allTickets.filter((t) => t.assigned_to === selectedWorker);

        // Sort: open tickets first (not RESUELTO/ELIMINADO), then resolved
        return tickets.sort((a, b) => {
            const aOpen = a.estado !== 'RESUELTO' && a.estado !== 'ELIMINADO';
            const bOpen = b.estado !== 'RESUELTO' && b.estado !== 'ELIMINADO';

            if (aOpen && !bOpen) return -1;
            if (!aOpen && bOpen) return 1;
            return 0; // same status, keep original order
        });
    }, [allTickets, selectedWorker]);

    // Calculate recurring groups
    const recurringGroups = useMemo(() => {
        // NOTA: usando 'area' como Tipo - no existe campo tipo/category en modelo Ticket
        const groupMap = new Map<string, RecurringGroup>();

        allTickets.forEach((ticket) => {
            const type = ticket.area; // fallback: usar area como tipo
            const location = ticket.ubicacion || '-';
            const key = `${type}||${location}`;

            if (!groupMap.has(key)) {
                groupMap.set(key, {
                    type,
                    location,
                    count: 0,
                    lastCreated: ticket.created_at,
                    ticketIds: [],
                });
            }

            const group = groupMap.get(key)!;
            group.count++;
            group.ticketIds.push(ticket.id);
            // Update last created if this ticket is more recent
            if (new Date(ticket.created_at) > new Date(group.lastCreated)) {
                group.lastCreated = ticket.created_at;
            }
        });

        // Convert to array and sort by count desc, then lastCreated desc
        const groups = Array.from(groupMap.values());
        return groups.sort((a, b) => {
            if (b.count !== a.count) return b.count - a.count;
            return new Date(b.lastCreated).getTime() - new Date(a.lastCreated).getTime();
        });
    }, [allTickets]);

    // Get tickets for selected recurring group (sorted by most recent first)
    const recurringGroupTickets = useMemo(() => {
        if (!selectedRecurringGroup) return [];
        const tickets = allTickets.filter((t) => selectedRecurringGroup.ticketIds.includes(t.id));
        // Sort by created_at descending (most recent first)
        return tickets.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    }, [allTickets, selectedRecurringGroup]);

    // Sort quality breakdown by overdue count (desc)
    const sortedBreakdown = qualityData?.breakdown
        ? [...qualityData.breakdown].sort((a, b) => b.overdue - a.overdue)
        : [];

    // Check if data is empty
    const isEmpty =
        (activeTab === 'summary' && summaryData && summaryData.open_count === 0 && summaryData.overdue_count === 0) ||
        (activeTab === 'quality' && sortedBreakdown.length === 0) ||
        (activeTab === 'performance' && workerPerformance.length === 0) ||
        (activeTab === 'recurring' && recurringGroups.length === 0);

    const handleRetry = () => {
        if (activeTab === 'summary') fetchSummary();
        else if (activeTab === 'quality') fetchQuality();
        else fetchAllTickets();
    };

    return (
        <div className="metricsPage">
            <header className="metricsHeader">
                <h1>Métricas</h1>

                {/* Period Filter */}
                <div className="metricsFilters">
                    <label htmlFor="period-select">Periodo:</label>
                    <select
                        id="period-select"
                        value={period}
                        onChange={(e) => setPeriod(e.target.value as MetricsPeriod)}
                        className="periodSelect"
                    >
                        <option value="today">Hoy</option>
                        <option value="yesterday">Ayer</option>
                        <option value="7d">Últimos 7 días</option>
                        <option value="30d">Últimos 30 días</option>
                        <option value="all">Todo el tiempo</option>
                    </select>
                </div>
            </header>

            {/* Tabs */}
            <div className="metricsTabs">
                <button
                    className={`tabButton ${activeTab === 'summary' ? 'active' : ''}`}
                    onClick={() => setActiveTab('summary')}
                >
                    Resumen
                </button>
                <button
                    className={`tabButton ${activeTab === 'quality' ? 'active' : ''}`}
                    onClick={() => setActiveTab('quality')}
                >
                    Calidad
                </button>
                <button
                    className={`tabButton ${activeTab === 'performance' ? 'active' : ''}`}
                    onClick={() => setActiveTab('performance')}
                >
                    Desempeño
                </button>
                <button
                    className={`tabButton ${activeTab === 'recurring' ? 'active' : ''}`}
                    onClick={() => setActiveTab('recurring')}
                >
                    Reincidentes
                </button>
            </div>

            {/* Content */}
            <div className="metricsContent">
                {/* Loading State */}
                {isLoading && (
                    <div className="metricsState">
                        <p>Cargando…</p>
                    </div>
                )}

                {/* Error State */}
                {!isLoading && error && (
                    <div className="metricsState metricsError">
                        <p>{error}</p>
                        <button onClick={handleRetry} className="retryButton">
                            Reintentar
                        </button>
                    </div>
                )}

                {/* Empty State */}
                {!isLoading && !error && isEmpty && (
                    <div className="metricsState">
                        <p>Sin datos para el periodo seleccionado</p>
                    </div>
                )}

                {/* Summary Tab */}
                {!isLoading && !error && activeTab === 'summary' && summaryData && !isEmpty && (
                    <div className="summaryTab">
                        <div className="kpiCards">
                            <div className="kpiCard">
                                <div className="kpiValue">{summaryData.open_count}</div>
                                <div className="kpiLabel">Abiertos</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">{summaryData.overdue_count}</div>
                                <div className="kpiLabel">Vencidos</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">{summaryData.at_risk_count}</div>
                                <div className="kpiLabel">En Riesgo</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">
                                    {summaryData.avg_resolution_minutes_7d
                                        ? Math.round(summaryData.avg_resolution_minutes_7d)
                                        : 0}
                                </div>
                                <div className="kpiLabel">Minutos Promedio (7d)</div>
                            </div>
                        </div>

                        {/* Additional info */}
                        <div className="summaryFooter">
                            {summaryData.resolved_7d !== undefined && (
                                <p className="summaryInfo">Resueltos (7d): {summaryData.resolved_7d}</p>
                            )}
                            {summaryData.at && (
                                <p className="summaryInfo">
                                    Actualizado: {new Date(summaryData.at).toLocaleString('es-ES')}
                                </p>
                            )}
                        </div>
                    </div>
                )}

                {/* Quality Tab */}
                {!isLoading && !error && activeTab === 'quality' && !isEmpty && (
                    <div className="qualityTab">
                        <table className="qualityTable">
                            <thead>
                                <tr>
                                    <th>Área</th>
                                    <th>Abiertos</th>
                                    <th>Vencidos</th>
                                    <th>Minutos Promedio (7d)</th>
                                    {sortedBreakdown.some((row) => row.sla_pct !== undefined) && <th>SLA %</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {sortedBreakdown.map((row: MetricsQualityRow) => (
                                    <tr key={row.area}>
                                        <td className="areaCell">{row.area}</td>
                                        <td>{row.open}</td>
                                        <td className={row.overdue > 0 ? 'overdueCell' : ''}>{row.overdue}</td>
                                        <td>{row.avg_resolution_minutes_7d ? Math.round(row.avg_resolution_minutes_7d) : 0}</td>
                                        {row.sla_pct !== undefined && <td>{row.sla_pct}%</td>}
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {qualityData?.at && (
                            <p className="qualityFooter">
                                Actualizado: {new Date(qualityData.at).toLocaleString('es-ES')}
                            </p>
                        )}
                    </div>
                )}

                {/* Performance Tab */}
                {!isLoading && !error && activeTab === 'performance' && !isEmpty && (
                    <div className="performanceTab">
                        {selectedWorker === null ? (
                            // Worker performance table
                            <table className="performanceTable">
                                <thead>
                                    <tr>
                                        <th>Usuario</th>
                                        <th>Asignados Abiertos</th>
                                        <th>En Curso</th>
                                        <th>Resueltos (30d)</th>
                                        <th>TTR prom. (min)</th>
                                        <th>SLA %</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {workerPerformance.map((worker) => (
                                        <tr
                                            key={worker.userId}
                                            onClick={() => setSelectedWorker(worker.userId)}
                                            className="clickableRow"
                                        >
                                            <td>{worker.userName}</td>
                                            <td>{worker.assignedOpen}</td>
                                            <td>{worker.inProgress}</td>
                                            <td>{worker.resolved30d}</td>
                                            <td>{worker.avgTTRMinutes}</td>
                                            <td>{worker.slaPercentage !== null ? `${worker.slaPercentage}%` : '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            // Worker tickets detail
                            <div className="workerDetail">
                                <div className="detailHeader">
                                    <button onClick={() => setSelectedWorker(null)} className="backButton">
                                        ← Volver
                                    </button>
                                    <h3>Tickets de {getUserName(selectedWorker)}</h3>
                                </div>

                                <table className="workerTicketsTable">
                                    <thead>
                                        <tr>
                                            <th>#ID</th>
                                            <th>Estado</th>
                                            <th>Prioridad</th>
                                            <th>Área</th>
                                            <th>Ubicación</th>
                                            <th>Creado</th>
                                            <th>Due</th>
                                            <th>SLA</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {workerTickets.map((ticket) => {
                                            const slaStatus = getSLAStatus(ticket);
                                            return (
                                                <tr
                                                    key={ticket.id}
                                                    onClick={() => navigate(`/tickets/${ticket.id}`)}
                                                    className="clickableRow"
                                                >
                                                    <td className="mono">#{ticket.id}</td>
                                                    <td>
                                                        <Badge type="estado" value={ticket.estado} />
                                                    </td>
                                                    <td>
                                                        <Badge type="prioridad" value={ticket.prioridad} />
                                                    </td>
                                                    <td>{ticket.area}</td>
                                                    <td>{ticket.ubicacion || '-'}</td>
                                                    <td>{formatDateShort(ticket.created_at)}</td>
                                                    <td>{ticket.due_at ? formatDateShort(ticket.due_at) : '-'}</td>
                                                    <td>{slaStatus && <Badge type="sla" value={slaStatus} />}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}

                {/* Recurring Tab */}
                {!isLoading && !error && activeTab === 'recurring' && !isEmpty && (
                    <div className="recurringTab">
                        {selectedRecurringGroup === null ? (
                            // Recurring groups table
                            <table className="recurringTable">
                                <thead>
                                    <tr>
                                        <th>Tipo</th>
                                        <th>Ubicación</th>
                                        <th>Incidencias</th>
                                        <th>Último</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {recurringGroups.map((group, idx) => (
                                        <tr
                                            key={idx}
                                            onClick={() => setSelectedRecurringGroup(group)}
                                            className="clickableRow"
                                        >
                                            <td>{group.type}</td>
                                            <td>{group.location}</td>
                                            <td>{group.count}</td>
                                            <td>{formatDate(group.lastCreated)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            // Recurring group tickets detail
                            <div className="recurringDetail">
                                <div className="detailHeader">
                                    <button onClick={() => setSelectedRecurringGroup(null)} className="backButton">
                                        ← Volver
                                    </button>
                                    <h3>
                                        {selectedRecurringGroup.type} - {selectedRecurringGroup.location} (
                                        {selectedRecurringGroup.count} incidencias)
                                    </h3>
                                </div>

                                <table className="recurringTicketsTable">
                                    <thead>
                                        <tr>
                                            <th>#ID</th>
                                            <th>Estado</th>
                                            <th>Prioridad</th>
                                            <th>Detalle</th>
                                            <th>Creado</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {recurringGroupTickets.map((ticket) => (
                                            <tr
                                                key={ticket.id}
                                                onClick={() => navigate(`/tickets/${ticket.id}`)}
                                                className="clickableRow"
                                            >
                                                <td className="mono">#{ticket.id}</td>
                                                <td>
                                                    <Badge type="estado" value={ticket.estado} />
                                                </td>
                                                <td>
                                                    <Badge type="prioridad" value={ticket.prioridad} />
                                                </td>
                                                <td className="detailCell">{ticket.detalle}</td>
                                                <td>{formatDate(ticket.created_at)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
