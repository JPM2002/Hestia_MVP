import { useNavigate } from 'react-router-dom';
import './AdminUsersPage.css';

interface MockUser {
    id: number;
    name: string;
    email: string;
    role: string;
    org: string;
    hotel: string;
    status: 'activo' | 'inactivo';
}

const MOCK_USERS: MockUser[] = [
    { id: 1, name: 'Ana García', email: 'ana.garcia@hotel.com', role: 'GERENTE', org: 'Hotel Group A', hotel: 'Hotel Plaza', status: 'activo' },
    { id: 2, name: 'Carlos Pérez', email: 'carlos.perez@hotel.com', role: 'RECEPCION', org: 'Hotel Group A', hotel: 'Hotel Plaza', status: 'activo' },
    { id: 3, name: 'María López', email: 'maria.lopez@hotel.com', role: 'TECNICO', org: 'Cadena Hotelera B', hotel: 'Hotel Mar Azul', status: 'activo' },
    { id: 4, name: 'Juan Rodríguez', email: 'juan.rodriguez@hotel.com', role: 'SUPERVISOR', org: 'Cadena Hotelera B', hotel: 'Hotel Mar Azul', status: 'activo' },
    { id: 5, name: 'Laura Martínez', email: 'laura.martinez@hotel.com', role: 'TECNICO', org: 'Resorts C', hotel: 'Resort Mountain View', status: 'activo' },
    { id: 6, name: 'Pedro Sánchez', email: 'pedro.sanchez@hotel.com', role: 'RECEPCION', org: 'Hotel Group A', hotel: 'Hotel Centro', status: 'activo' },
    { id: 7, name: 'Sofía Fernández', email: 'sofia.fernandez@hotel.com', role: 'GERENTE', org: 'Resorts C', hotel: 'Resort Mountain View', status: 'activo' },
    { id: 8, name: 'Diego Torres', email: 'diego.torres@hotel.com', role: 'TECNICO', org: 'Cadena Hotelera B', hotel: 'Grand Palace', status: 'inactivo' },
    { id: 9, name: 'Carmen Ruiz', email: 'carmen.ruiz@hotel.com', role: 'SUPERVISOR', org: 'Hotel Group A', hotel: 'Hotel Plaza', status: 'activo' },
    { id: 10, name: 'Roberto Díaz', email: 'roberto.diaz@hotel.com', role: 'RECEPCION', org: 'Cadena Hotelera B', hotel: 'Hotel Mar Azul', status: 'activo' },
    { id: 11, name: 'Elena Morales', email: 'elena.morales@hotel.com', role: 'TECNICO', org: 'Resorts C', hotel: 'Resort Mountain View', status: 'activo' },
    { id: 12, name: 'Miguel Castro', email: 'miguel.castro@hotel.com', role: 'SUPERADMIN', org: 'Sistema', hotel: '-', status: 'activo' },
];

export function AdminUsersPage() {
    const navigate = useNavigate();

    const handleEdit = (userId: number) => {
        // Dummy action for demo
        alert(`Editar usuario #${userId} (función pendiente)`);
    };

    const handleChangeRole = (userId: number) => {
        // Dummy action for demo
        alert(`Cambiar rol de usuario #${userId} (función pendiente)`);
    };

    return (
        <div className="adminUsersPage">
            <header className="adminUsersHeader">
                <button onClick={() => navigate('/admin')} className="backButton">
                    ← Volver
                </button>
                <h1>Gestión de Usuarios</h1>
            </header>

            <div className="usersContent">
                <table className="usersTable">
                    <thead>
                        <tr>
                            <th>Nombre</th>
                            <th>Email</th>
                            <th>Rol</th>
                            <th>Organización</th>
                            <th>Hotel</th>
                            <th>Estado</th>
                            <th>Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {MOCK_USERS.map((user) => (
                            <tr key={user.id}>
                                <td className="userName">{user.name}</td>
                                <td className="userEmail">{user.email}</td>
                                <td>
                                    <span className={`roleBadge ${user.role.toLowerCase()}`}>
                                        {user.role}
                                    </span>
                                </td>
                                <td>{user.org}</td>
                                <td>{user.hotel}</td>
                                <td>
                                    <span className={`statusBadge ${user.status}`}>
                                        {user.status === 'activo' ? 'Activo' : 'Inactivo'}
                                    </span>
                                </td>
                                <td>
                                    <div className="actionButtons">
                                        <button
                                            onClick={() => handleEdit(user.id)}
                                            className="actionBtn editBtn"
                                        >
                                            Editar
                                        </button>
                                        <button
                                            onClick={() => handleChangeRole(user.id)}
                                            className="actionBtn roleBtn"
                                        >
                                            Cambiar Rol
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
