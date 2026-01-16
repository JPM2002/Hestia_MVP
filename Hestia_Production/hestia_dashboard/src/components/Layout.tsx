import { type ReactNode, useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import type { Role } from '../auth/permissions';
import './Layout.css';

interface LayoutProps {
    children: ReactNode;
    onLogout?: () => void;
    user?: { name: string; role: string } | null;
}

const SIDEBAR_STORAGE_KEY = 'sidebarCollapsed';

export function Layout({ children, onLogout, user }: LayoutProps) {
    // Initialize collapsed state from localStorage
    const [isCollapsed, setIsCollapsed] = useState(() => {
        const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
        return stored === 'true';
    });

    // Persist collapsed state to localStorage
    useEffect(() => {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isCollapsed));
    }, [isCollapsed]);

    const handleToggle = () => {
        setIsCollapsed((prev) => !prev);
    };

    const userRole = (user?.role as Role) || 'RECEPCION';

    return (
        <div className="app">
            <header className="topbar">
                <div className="topbarLeft">
                    <button
                        className="menuToggle"
                        onClick={handleToggle}
                        aria-label="Toggle menu"
                        title="Toggle sidebar"
                    >
                        ☰
                    </button>

                    <div className="brand">
                        <div className="brandMark">H</div>
                        <div>
                            <div className="brandName">Hestia</div>
                            <div className="brandTag">Hotel Operations Dashboard</div>
                        </div>
                    </div>
                </div>

                {user && (
                    <div className="userChip" title={user.name}>
                        <span className="userDot" />
                        {user.name}
                        {onLogout && (
                            <button onClick={onLogout} className="logoutBtn" title="Cerrar sesión">
                                ×
                            </button>
                        )}
                    </div>
                )}
            </header>

            <div className="layoutBody">
                <Sidebar
                    userRole={userRole}
                    isCollapsed={isCollapsed}
                    onToggle={handleToggle}
                />

                <main className={`mainContent ${isCollapsed ? 'sidebarCollapsed' : ''}`}>
                    <div className="container">{children}</div>

                    <footer className="footer">
                        <span>Hestia MVP • React + TypeScript</span>
                    </footer>
                </main>
            </div>
        </div>
    );
}
