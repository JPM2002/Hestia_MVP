import { NavLink } from 'react-router-dom';
import { filterNavByRole, type Role } from '../auth/permissions';
import { NAV_ITEMS } from '../auth/permissions';
import './Sidebar.css';

interface SidebarProps {
    userRole: Role;
    isCollapsed: boolean;
    onToggle: () => void;
}

export function Sidebar({ userRole, isCollapsed, onToggle }: SidebarProps) {
    const filteredNavItems = filterNavByRole(NAV_ITEMS, userRole);

    return (
        <aside
            className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}
            aria-label="Navegación principal"
            id="sidebar"
        >
            <nav className="sidebarNav">
                {filteredNavItems.map((item) => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        end={item.end}
                        className={({ isActive }) =>
                            `sidebarLink ${isActive ? 'active' : ''}`
                        }
                        title={isCollapsed ? item.label : undefined}
                    >
                        <span className="sidebarIcon" aria-hidden="true">
                            {item.icon}
                        </span>
                        <span className="sidebarLabel">{item.label}</span>
                    </NavLink>
                ))}
            </nav>

            <button
                className="sidebarToggle"
                onClick={onToggle}
                aria-expanded={!isCollapsed}
                aria-controls="sidebar"
                aria-label={isCollapsed ? 'Expandir sidebar' : 'Colapsar sidebar'}
            >
                {isCollapsed ? '→' : '←'}
            </button>
        </aside>
    );
}
