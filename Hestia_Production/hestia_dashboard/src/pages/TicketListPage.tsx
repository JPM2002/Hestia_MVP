// Enhanced Tickets List Page with demo UI
export function TicketListPage() {
    return (
        <div className="ticketsPage">
            <div className="pageHeader">
                <h1>Tickets</h1>
                <p>Gestión de tickets de soporte</p>
            </div>

            {/* Stats Cards */}
            <div className="statsGrid">
                <div className="statCard">
                    <div className="statLabel">Total Tickets</div>
                    <div className="statValue">24</div>
                    <div className="statHint">Últimos 30 días</div>
                </div>
                <div className="statCard">
                    <div className="statLabel">Pendientes</div>
                    <div className="statValue">12</div>
                    <div className="statHint">Requieren atención</div>
                </div>
                <div className="statCard">
                    <div className="statLabel">Resueltos</div>
                    <div className="statValue">8</div>
                    <div className="statHint">Esta semana</div>
                </div>
            </div>

            {/* Tickets Table Skeleton */}
            <div className="tableCard">
                <div className="tableHeader">
                    <h2>Tickets Recientes</h2>
                </div>
                <div className="tableWrapper">
                    <table className="ticketsTable">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Cliente</th>
                                <th>Asunto</th>
                                <th>Estado</th>
                                <th>Prioridad</th>
                                <th>Fecha</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td className="mono">#TK-001</td>
                                <td>María González</td>
                                <td>Problema con la reserva</td>
                                <td><span className="badge badge-pending">Pendiente</span></td>
                                <td><span className="badge badge-high">Alta</span></td>
                                <td>15/01/2026</td>
                            </tr>
                            <tr>
                                <td className="mono">#TK-002</td>
                                <td>Carlos Pérez</td>
                                <td>Consulta sobre servicios</td>
                                <td><span className="badge badge-progress">En Progreso</span></td>
                                <td><span className="badge badge-medium">Media</span></td>
                                <td>15/01/2026</td>
                            </tr>
                            <tr>
                                <td className="mono">#TK-003</td>
                                <td>Ana Martínez</td>
                                <td>Modificación de fechas</td>
                                <td><span className="badge badge-resolved">Resuelto</span></td>
                                <td><span className="badge badge-low">Baja</span></td>
                                <td>14/01/2026</td>
                            </tr>
                            <tr>
                                <td className="mono">#TK-004</td>
                                <td>Luis Fernández</td>
                                <td>Facturación incorrecta</td>
                                <td><span className="badge badge-pending">Pendiente</span></td>
                                <td><span className="badge badge-high">Alta</span></td>
                                <td>14/01/2026</td>
                            </tr>
                            <tr>
                                <td className="mono">#TK-005</td>
                                <td>Sofia Ramírez</td>
                                <td>Solicitud de información</td>
                                <td><span className="badge badge-progress">En Progreso</span></td>
                                <td><span className="badge badge-medium">Media</span></td>
                                <td>13/01/2026</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
