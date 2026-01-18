import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import type { User } from '../types/api';
import { login as apiLogin, logout as apiLogout } from '../services/api';
import { APIClientError } from '../api/client';

// localStorage key for session persistence
const AUTH_STORAGE_KEY = 'hestia.auth.user';
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

interface AuthContextType {
    user: User | null;
    isAuthenticated: boolean;
    loginMock: (role: User['role']) => void;
    loginReal: (email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const navigate = useNavigate();

    // Restore session from localStorage on mount
    useEffect(() => {
        const stored = localStorage.getItem(AUTH_STORAGE_KEY);
        if (stored) {
            try {
                const userData = JSON.parse(stored);
                setUser(userData);
            } catch {
                localStorage.removeItem(AUTH_STORAGE_KEY);
            }
        }
    }, []);

    // Save to localStorage whenever user changes
    useEffect(() => {
        if (user) {
            localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        } else {
            localStorage.removeItem(AUTH_STORAGE_KEY);
        }
    }, [user]);

    const loginMock = (role: User['role']) => {
        const mockUser: User = {
            id: 1,
            name: `Usuario ${role}`,
            email: 'demo@hestia.local',
            role,
            area: role === 'TECNICO' ? 'MANTENCION' : undefined,
            is_superadmin: false,
        };
        setUser(mockUser);
        navigate('/tickets');
    };

    const loginReal = async (email: string, password: string) => {
        try {
            await apiLogin(email, password);

            // Session established via cookie. Create user object.
            // In real mode, we don't have /api/me, so we construct minimal user data
            const realUser: User = {
                id: 0, // Backend doesn't return this from login
                name: email.split('@')[0], // Use email prefix as name
                email,
                role: 'RECEPCION', // Default role - backend should provide this
                is_superadmin: false,
            };

            setUser(realUser);
            navigate('/tickets');
        } catch (error) {
            if (error instanceof APIClientError) {
                throw error;
            }
            throw new APIClientError(0, 'network', 'Error de conexión');
        }
    };

    const logout = async () => {
        try {
            if (!USE_MOCKS) {
                await apiLogout();
            }
        } finally {
            setUser(null);
            navigate('/login');
        }
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                isAuthenticated: !!user,
                loginMock,
                loginReal,
                logout,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
}
