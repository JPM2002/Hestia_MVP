import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getTickets } from '../services/api';
import type { Ticket } from '../types/api';
import { Badge } from '../components/Badge';
import { getSLAStatus, formatDateShort } from '../utils/formatters';
import './OverviewPage.css';

export function OverviewPage() {
    const navigate = useNavigate();
    const [tickets, setTickets] = useState<Ticket[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchTickets = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await getTickets({});
            setTickets(response.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar datos');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchTickets();
    }, []);

    // Calculate KPIs
    const kpis = useMemo(() => {
        const now = new Date();
        const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

        // Críticos: pendientes (PENDIENTE + PENDIENTE_APROBACION) + prioridad alta/urgente
        const critical = tickets.filter(
            (t) =>
                (t.estado === 'PENDIENTE' || t.estado === 'PENDIENTE_APROBACION') &&
                (t.prioridad === 'ALTA' || t.prioridad === 'URGENTE')
        ).length;

        // Abiertos: != RESUELTO && != ELIMINADO
        const open = tickets.filter(
            (t) => t.estado !== 'RESUELTO' && t.estado !== 'ELIMINADO'
        ).length;

        // En curso: EN_CURSO + PAUSADO + ACEPTADO
        const inProgress = tickets.filter(
            (t) => t.estado === 'EN_CURSO' || t.estado === 'PAUSADO' || t.estado === 'ACEPTADO'
        ).length;

        // Resueltos (30d): estado == RESUELTO y finished_at dentro de últimos 30 días
        const resolved30d = tickets.filter((t) => {
            if (t.estado !== 'RESUELTO' || !t.finished_at) return false;
            const finishedDate = new Date(t.finished_at);
            return finishedDate >= thirtyDaysAgo;
        });

        // TTR prom (min, 30d): promedio de (finished_at - created_at) en minutos
        const ttrValues = resolved30d.map((t) => {
            const created = new Date(t.created_at).getTime();
            const finished = new Date(t.finished_at!).getTime();
            return Math.max(0, Math.round((finished - created) / 60000));
        });

        const avgTTR =
            ttrValues.length > 0
                ? Math.round(ttrValues.reduce((a, b) => a + b, 0) / ttrValues.length)
                : 0;

        // SLA % global: en resueltos (30d) con due_at: finished_at <= due_at / total_con_due_at * 100
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

        return {
            critical,
            open,
            inProgress,
            resolved30d: resolved30d.length,
            avgTTR,
            slaPercentage,
        };
    }, [tickets]);

    // Get últimos críticos (top 5)
    const recentCritical = useMemo(() => {
        const critical = tickets.filter(
            (t) =>
                (t.estado === 'PENDIENTE' || t.estado === 'PENDIENTE_APROBACION') &&
                (t.prioridad === 'ALTA' || t.prioridad === 'URGENTE')
        );
        // Sort by created_at desc (most recent first)
        const sorted = critical.sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        return sorted.slice(0, 5);
    }, [tickets]);

    const handleRetry = () => {
        fetchTickets();
    };

    const isEmpty = tickets.length === 0;

    return (
        <div className="overviewPage">
            <header className="overviewHeader">
                <h1>Overview</h1>
            </header>

            <div className="overviewContent">
                {/* Loading State */}
                {isLoading && (
                    <div className="overviewState">
                        <p>Cargando…</p>
                    </div>
                )}

                {/* Error State */}
                {!isLoading && error && (
                    <div className="overviewState overviewError">
                        <p>{error}</p>
                        <button onClick={handleRetry} className="retryButton">
                            Reintentar
                        </button>
                    </div>
                )}

                {/* Empty State */}
                {!isLoading && !error && isEmpty && (
                    <div className="overviewState">
                        <p>Sin datos disponibles</p>
                    </div>
                )}

                {/* Content */}
                {!isLoading && !error && !isEmpty && (
                    <>
                        {/* KPI Cards */}
                        <div className="kpiCards">
                            <div className="kpiCard critical">
                                <div className="kpiValue">{kpis.critical}</div>
                                <div className="kpiLabel">Críticos</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">{kpis.open}</div>
                                <div className="kpiLabel">Abiertos</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">{kpis.inProgress}</div>
                                <div className="kpiLabel">En Curso</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">{kpis.resolved30d}</div>
                                <div className="kpiLabel">Resueltos (30d)</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">
                                    {kpis.slaPercentage !== null ? `${kpis.slaPercentage}%` : '-'}
                                </div>
                                <div className="kpiLabel">SLA % Global</div>
                            </div>

                            <div className="kpiCard">
                                <div className="kpiValue">{kpis.avgTTR}</div>
                                <div className="kpiLabel">TTR Prom (min)</div>
                            </div>
                        </div>

                        {/* Últimos Críticos */}
                        <div className="criticalSection">
                            <h2>Últimos Críticos</h2>
                            {recentCritical.length === 0 ? (
                                <p className="emptyMessage">No hay tickets críticos actualmente</p>
                            ) : (
                                <table className="criticalTable">
                                    <thead>
                                        <tr>
                                            <th>#ID</th>
                                            <th>Estado</th>
                                            <th>Prioridad</th>
                                            <th>Ubicación</th>
                                            <th>Creado</th>
                                            <th>SLA</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {recentCritical.map((ticket) => {
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
                                                    <td>{ticket.ubicacion || '-'}</td>
                                                    <td>{formatDateShort(ticket.created_at)}</td>
                                                    <td>{slaStatus && <Badge type="sla" value={slaStatus} />}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
