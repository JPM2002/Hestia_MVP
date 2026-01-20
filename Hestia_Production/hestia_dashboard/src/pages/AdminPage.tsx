import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import './AdminPage.css';

export function AdminPage() {
    const navigate = useNavigate();
    const [selectedOrg, setSelectedOrg] = useState('all');
    const [selectedHotel, setSelectedHotel] = useState('all');

    // Mock data
    const stats = {
        orgs: 3,
        hotels: 8,
        users: 15,
        tickets: 127,
    };

    const mockOrgs = [
        { id: 'all', name: 'Todas las organizaciones' },
        { id: 'org1', name: 'Hotel Group A' },
        { id: 'org2', name: 'Cadena Hotelera B' },
        { id: 'org3', name: 'Resorts C' },
    ];

    const mockHotels = [
        { id: 'all', name: 'Todos los hoteles' },
        { id: 'h1', name: 'Hotel Plaza' },
        { id: 'h2', name: 'Hotel Mar Azul' },
        { id: 'h3', name: 'Resort Mountain View' },
        { id: 'h4', name: 'Hotel Centro' },
        { id: 'h5', name: 'Grand Palace' },
    ];

    return (
        <div className="adminPage">
            <header className="adminHeader">
                <h1>Administración</h1>
            </header>

            {/* Selectors */}
            <div className="adminSelectors">
                <div className="selectorGroup">
                    <label htmlFor="org-select">Organización:</label>
                    <select
                        id="org-select"
                        value={selectedOrg}
                        onChange={(e) => setSelectedOrg(e.target.value)}
                        className="adminSelect"
                    >
                        {mockOrgs.map((org) => (
                            <option key={org.id} value={org.id}>
                                {org.name}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="selectorGroup">
                    <label htmlFor="hotel-select">Hotel:</label>
                    <select
                        id="hotel-select"
                        value={selectedHotel}
                        onChange={(e) => setSelectedHotel(e.target.value)}
                        className="adminSelect"
                    >
                        {mockHotels.map((hotel) => (
                            <option key={hotel.id} value={hotel.id}>
                                {hotel.name}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="adminStats">
                <div className="statCard">
                    <div className="statValue">{stats.orgs}</div>
                    <div className="statLabel">Organizaciones</div>
                </div>

                <div className="statCard">
                    <div className="statValue">{stats.hotels}</div>
                    <div className="statLabel">Hoteles</div>
                </div>

                <div className="statCard">
                    <div className="statValue">{stats.users}</div>
                    <div className="statLabel">Usuarios</div>
                </div>

                <div className="statCard">
                    <div className="statValue">{stats.tickets}</div>
                    <div className="statLabel">Tickets Totales</div>
                </div>
            </div>

            {/* Quick Access */}
            <div className="quickAccess">
                <h2>Accesos Rápidos</h2>
                <div className="accessCards">
                    <button
                        className="accessCard"
                        onClick={() => navigate('/admin/users')}
                    >
                        <span className="accessIcon">👥</span>
                        <span className="accessLabel">Gestión de Usuarios</span>
                        <span className="accessArrow">→</span>
                    </button>

                    <button
                        className="accessCard"
                        onClick={() => navigate('/admin/orgs-hotels')}
                    >
                        <span className="accessIcon">🏢</span>
                        <span className="accessLabel">Organizaciones y Hoteles</span>
                        <span className="accessArrow">→</span>
                    </button>
                </div>
            </div>
        </div>
    );
}
