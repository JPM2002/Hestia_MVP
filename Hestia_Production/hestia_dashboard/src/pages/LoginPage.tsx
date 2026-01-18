import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import type { User } from '../types/api';
import { APIClientError } from '../api/client';
import './LoginPage.css';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

export function LoginPage() {
    const navigate = useNavigate();
    const { isAuthenticated, loginMock, loginReal } = useAuth();
    const [selectedRole, setSelectedRole] = useState<User['role']>('RECEPCION');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    // Redirect if already authenticated
    useEffect(() => {
        if (isAuthenticated) {
            navigate('/tickets');
        }
    }, [isAuthenticated, navigate]);

    const handleMockLogin = (e: React.FormEvent) => {
        e.preventDefault();
        loginMock(selectedRole);
    };

    const handleRealLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            await loginReal(email, password);
        } catch (err) {
            if (err instanceof APIClientError) {
                setError(err.message);
            } else {
                setError('Error de conexión');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            <div className="login-container">
                <div className="login-header">
                    <h1>Hestia Dashboard</h1>
                    <p>Sistema de Gestión Hotelera</p>
                </div>

                {USE_MOCKS ? (
                    // Mock Mode: Role selector
                    <form onSubmit={handleMockLogin} className="login-form">
                        <div className="mode-badge">Modo: DEMO</div>

                        <div className="form-group">
                            <label htmlFor="role">Seleccionar Rol:</label>
                            <select
                                id="role"
                                value={selectedRole}
                                onChange={(e) => setSelectedRole(e.target.value as User['role'])}
                                className="form-select"
                            >
                                <option value="RECEPCION">Recepción</option>
                                <option value="TECNICO">Técnico</option>
                                <option value="SUPERVISOR">Supervisor</option>
                                <option value="GERENTE">Gerente</option>
                                <option value="SUPERADMIN">Superadmin</option>
                            </select>
                        </div>

                        <button type="submit" className="btn-login">
                            Entrar como Demo
                        </button>

                        <p className="login-hint">
                            💡 Cambia el rol para ver diferentes permisos en el Sidebar
                        </p>
                    </form>
                ) : (
                    // Real Mode: Email/Password
                    <form onSubmit={handleRealLogin} className="login-form">
                        <div className="mode-badge mode-real">Modo: PRODUCCIÓN</div>

                        {error && <div className="error-message">{error}</div>}

                        <div className="form-group">
                            <label htmlFor="email">Email:</label>
                            <input
                                id="email"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="form-input"
                                placeholder="usuario@hotel.com"
                                required
                                disabled={loading}
                            />
                        </div>

                        <div className="form-group">
                            <label htmlFor="password">Contraseña:</label>
                            <input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="form-input"
                                placeholder="••••••••"
                                required
                                disabled={loading}
                            />
                        </div>

                        <button type="submit" className="btn-login" disabled={loading}>
                            {loading ? 'Ingresando...' : 'Ingresar'}
                        </button>
                    </form>
                )}
            </div>
        </div>
    );
}
