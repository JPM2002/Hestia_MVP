// Role-based permissions and navigation

export type Role = 'RECEPCION' | 'TECNICO' | 'SUPERVISOR' | 'GERENTE' | 'SUPERADMIN';

export interface NavItem {
  path: string;
  label: string;
  icon: string;
  allowedRoles: Role[];
  end?: boolean; // Exact match for active state
}

export const NAV_ITEMS: NavItem[] = [
  {
    path: '/tickets',
    label: 'Tickets',
    icon: '🎫',
    allowedRoles: ['RECEPCION', 'TECNICO', 'SUPERVISOR', 'GERENTE', 'SUPERADMIN'],
    end: true, // Exact match for /tickets (won't be active on /tickets/:id)
  },
  {
    path: '/metrics',
    label: 'Métricas',
    icon: '📊',
    allowedRoles: ['GERENTE', 'SUPERADMIN'],
    end: true,
  },
  // Future routes (uncomment when implemented):
  // {
  //   path: '/reportes',
  //   label: 'Reportes',
  //   icon: '📈',
  //   allowedRoles: ['GERENTE', 'SUPERADMIN'],
  // },
  // {
  //   path: '/admin',
  //   label: 'Admin',
  //   icon: '⚙️',
  //   allowedRoles: ['SUPERADMIN'],
  // },
];

export function filterNavByRole(items: NavItem[], role: Role): NavItem[] {
  return items.filter((item) => item.allowedRoles.includes(role));
}
