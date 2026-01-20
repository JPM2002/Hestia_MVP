// src/components/ProtectedRoute.tsx
import { type ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import type { Role } from '../auth/permissions';

interface ProtectedRouteProps {
  children: ReactNode;
  isAuthenticated: boolean;
  redirectTo?: string;
  userRole?: Role;
  allowedRoles?: Role[];
}

export function ProtectedRoute({
  children,
  isAuthenticated,
  redirectTo = '/login',
  userRole,
  allowedRoles,
}: ProtectedRouteProps) {
  // 1) Auth
  if (!isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
  }

  // 2) Roles (si la ruta tiene restricción, debe existir rol y estar permitido)
  if (allowedRoles && allowedRoles.length > 0) {
    if (!userRole || !allowedRoles.includes(userRole)) {
      return <Navigate to="/tickets" replace />;
    }
  }

  return <>{children}</>;
}
