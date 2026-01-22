import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import type { User } from '../types/api';
import { APIClientError } from '../api/client';
import { Card } from '../ui/Card';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
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

    const roleOptions = [
        { value: 'RECEPCION', label: 'Recepción' },
        { value: 'TECNICO', label: 'Técnico' },
        { value: 'SUPERVISOR', label: 'Supervisor' },
        { value: 'GERENTE', label: 'Gerente' },
        { value: 'SUPERADMIN', label: 'Superadmin' },
    ];

    return (
        <div className="login-page">
            <div className="login-container">
                <div className="login-header">
                    <h1>Hestia Dashboard</h1>
                    <p>Sistema de Gestión Hotelera</p>
                </div>

                {USE_MOCKS ? (
                    // Mock Mode: Role selector
                    <Card>
                        <form onSubmit={handleMockLogin} className="login-form">
                            <div className="mode-badge">Modo: DEMO</div>

                            <Select
                                label="Seleccionar Rol:"
                                value={selectedRole}
                                onChange={(e) => setSelectedRole(e.target.value as User['role'])}
                                options={roleOptions}
                            />

                            <Button type="submit" variant="primary" style={{ width: '100%', marginTop: '1rem' }}>
                                Entrar como Demo
                            </Button>

                            <p className="login-hint">
                                💡 Cambia el rol para ver diferentes permisos en el Sidebar
                            </p>
                        </form>
                    </Card>
                ) : (
                    // Real Mode: Email/Password
                    <Card>
                        <form onSubmit={handleRealLogin} className="login-form">
                            <div className="mode-badge mode-real">Modo: PRODUCCIÓN</div>

                            {error && <div className="error-message">{error}</div>}

                            <Input
                                label="Email:"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="usuario@hotel.com"
                                required
                                disabled={loading}
                            />

                            <Input
                                label="Contraseña:"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                required
                                disabled={loading}
                            />

                            <Button
                                type="submit"
                                variant="primary"
                                disabled={loading}
                                loading={loading}
                                style={{ width: '100%', marginTop: '1rem' }}
                            >
                                Ingresar
                            </Button>
                        </form>
                    </Card>
                )}
            </div>
        </div>
    );
}
