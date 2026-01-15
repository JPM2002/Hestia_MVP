import { type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import './Layout.css';

interface LayoutProps {
    children: ReactNode;
    onLogout?: () => void;
    user?: { name: string; role: string } | null;
}

export function Layout({ children, onLogout, user }: LayoutProps) {
    return (
        <div className="app">
            <header className="topbar">
                <div className="brand">
                    <div className="brandMark">H</div>
                    <div>
                        <div className="brandName">Hestia</div>
                        <div className="brandTag">Hotel Operations Dashboard</div>
                    </div>
                </div>

                <nav className="nav">
                    <NavLink
                        to="/tickets"
                        className={({ isActive }) => (isActive ? 'navItem active' : 'navItem')}
                    >
                        Tickets
                    </NavLink>
                </nav>

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

            <main className="container">{children}</main>

            <footer className="footer">
                <span>Hestia MVP • React + TypeScript</span>
            </footer>
        </div>
    );
}
