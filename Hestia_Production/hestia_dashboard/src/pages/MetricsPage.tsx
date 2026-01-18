import { useState, useEffect } from 'react';
import { getMetricsSummary, getMetricsQuality } from '../services/api';
import type {
    MetricsSummaryResponse,
    MetricsQualityResponse,
    MetricsPeriod,
    MetricsQualityRow,
} from '../types/api';
import './MetricsPage.css';

type TabType = 'summary' | 'quality';

export function MetricsPage() {
    const [activeTab, setActiveTab] = useState<TabType>('summary');
    const [period, setPeriod] = useState<MetricsPeriod>('7d');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Summary data
    const [summaryData, setSummaryData] = useState<MetricsSummaryResponse | null>(null);

    // Quality data
    const [qualityData, setQualityData] = useState<MetricsQualityResponse | null>(null);

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

    // Load data when tab or period changes
    useEffect(() => {
        if (activeTab === 'summary') {
            fetchSummary();
        } else {
            fetchQuality();
        }
    }, [activeTab, period]);

    // Sort quality breakdown by overdue count (desc)
    const sortedBreakdown = qualityData?.breakdown
        ? [...qualityData.breakdown].sort((a, b) => b.overdue - a.overdue)
        : [];

    // Check if data is empty
    const isEmpty =
        (activeTab === 'summary' && summaryData && summaryData.open_count === 0 && summaryData.overdue_count === 0) ||
        (activeTab === 'quality' && sortedBreakdown.length === 0);

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
                        <button
                            onClick={() => (activeTab === 'summary' ? fetchSummary() : fetchQuality())}
                            className="retryButton"
                        >
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
            </div>
        </div>
    );
}
