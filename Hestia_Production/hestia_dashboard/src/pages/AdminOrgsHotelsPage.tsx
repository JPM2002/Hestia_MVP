import { useNavigate } from 'react-router-dom';
import './AdminOrgsHotelsPage.css';

interface MockOrgHotel {
    id: number;
    org: string;
    hotel: string;
    members: number;
    tickets: number;
    slaPercentage: number;
}

const MOCK_ORGS_HOTELS: MockOrgHotel[] = [
    { id: 1, org: 'Hotel Group A', hotel: 'Hotel Plaza', members: 12, tickets: 45, slaPercentage: 92.5 },
    { id: 2, org: 'Hotel Group A', hotel: 'Hotel Centro', members: 8, tickets: 28, slaPercentage: 87.3 },
    { id: 3, org: 'Cadena Hotelera B', hotel: 'Hotel Mar Azul', members: 15, tickets: 52, slaPercentage: 94.1 },
    { id: 4, org: 'Cadena Hotelera B', hotel: 'Grand Palace', members: 18, tickets: 67, slaPercentage: 89.7 },
    { id: 5, org: 'Resorts C', hotel: 'Resort Mountain View', members: 22, tickets: 78, slaPercentage: 91.2 },
    { id: 6, org: 'Hotel Group A', hotel: 'Hotel Vista Mar', members: 10, tickets: 34, slaPercentage: 85.6 },
    { id: 7, org: 'Cadena Hotelera B', hotel: 'Hotel Jardines', members: 14, tickets: 41, slaPercentage: 93.8 },
];

export function AdminOrgsHotelsPage() {
    const navigate = useNavigate();

    const handleView = (id: number) => {
        // Dummy action for demo
        alert(`Ver detalles de org/hotel #${id} (función pendiente)`);
    };

    const handleConfigure = (id: number) => {
        // Dummy action for demo
        alert(`Configurar org/hotel #${id} (función pendiente)`);
    };

    return (
        <div className="adminOrgsHotelsPage">
            <header className="adminOrgsHotelsHeader">
                <button onClick={() => navigate('/admin')} className="backButton">
                    ← Volver
                </button>
                <h1>Organizaciones y Hoteles</h1>
            </header>

            <div className="orgsHotelsContent">
                <table className="orgsHotelsTable">
                    <thead>
                        <tr>
                            <th>Organización</th>
                            <th>Hotel</th>
                            <th>Miembros</th>
                            <th>Tickets</th>
                            <th>SLA %</th>
                            <th>Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {MOCK_ORGS_HOTELS.map((item) => (
                            <tr key={item.id}>
                                <td className="orgName">{item.org}</td>
                                <td className="hotelName">{item.hotel}</td>
                                <td>{item.members}</td>
                                <td>{item.tickets}</td>
                                <td>
                                    <span className={`slaValue ${item.slaPercentage >= 90 ? 'good' : item.slaPercentage >= 80 ? 'medium' : 'low'}`}>
                                        {item.slaPercentage}%
                                    </span>
                                </td>
                                <td>
                                    <div className="actionButtons">
                                        <button
                                            onClick={() => handleView(item.id)}
                                            className="actionBtn viewBtn"
                                        >
                                            Ver
                                        </button>
                                        <button
                                            onClick={() => handleConfigure(item.id)}
                                            className="actionBtn configureBtn"
                                        >
                                            Configurar
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
