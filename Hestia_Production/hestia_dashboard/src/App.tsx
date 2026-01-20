import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorToast } from './components/ErrorToast';
import { LoginPage } from './pages/LoginPage';
import { OverviewPage } from './pages/OverviewPage';
import { TicketListPage } from './pages/TicketListPage';
import { TicketDetailPage } from './pages/TicketDetailPage';
import { MetricsPage } from './pages/MetricsPage';
import { AdminPage } from './pages/AdminPage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { AdminOrgsHotelsPage } from './pages/AdminOrgsHotelsPage';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { APIClientError } from './api/client';
import './App.css';

// Global error handler - can be called from anywhere
let globalErrorHandler: ((error: APIClientError) => void) | null = null;

export function setGlobalErrorHandler(handler: (error: APIClientError) => void) {
  globalErrorHandler = handler;
}

export function handleAPIError(error: unknown) {
  if (error instanceof APIClientError && globalErrorHandler) {
    globalErrorHandler(error);
  }
}

function AppContent() {
  const navigate = useNavigate();
  const [error, setError] = useState<{ message: string; type: APIClientError['type'] } | null>(null);
  const { isAuthenticated, user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
  };

  // Set up global error handler
  useEffect(() => {
    setGlobalErrorHandler((apiError: APIClientError) => {
      setError({
        message: apiError.message,
        type: apiError.type,
      });

      // Auto-redirect to login on 401
      if (apiError.status === 401) {
        setTimeout(() => {
          navigate('/login');
        }, 2000); // Give user time to read error
      }
    });

    return () => {
      globalErrorHandler = null;
    };
  }, [navigate]);

  return (
    <>
      <ErrorToast error={error} onClose={() => setError(null)} />

      <Routes>
        {/* Login route (public) */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes with Layout */}
        <Route
          path="/overview"
          element={
            <ProtectedRoute
              isAuthenticated={isAuthenticated}
              userRole={user?.role}
              allowedRoles={['GERENTE', 'SUPERADMIN']}
            >
              <Layout user={user} onLogout={handleLogout}>
                <OverviewPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/tickets"
          element={
            <ProtectedRoute isAuthenticated={isAuthenticated}>
              <Layout user={user} onLogout={handleLogout}>
                <TicketListPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/tickets/:id"
          element={
            <ProtectedRoute isAuthenticated={isAuthenticated}>
              <Layout user={user} onLogout={handleLogout}>
                <TicketDetailPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/metrics"
          element={
            <ProtectedRoute
              isAuthenticated={isAuthenticated}
              userRole={user?.role}
              allowedRoles={['GERENTE', 'SUPERADMIN']}
            >
              <Layout user={user} onLogout={handleLogout}>
                <MetricsPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin"
          element={
            <ProtectedRoute
              isAuthenticated={isAuthenticated}
              userRole={user?.role}
              allowedRoles={['SUPERADMIN']}
            >
              <Layout user={user} onLogout={handleLogout}>
                <AdminPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/users"
          element={
            <ProtectedRoute
              isAuthenticated={isAuthenticated}
              userRole={user?.role}
              allowedRoles={['SUPERADMIN']}
            >
              <Layout user={user} onLogout={handleLogout}>
                <AdminUsersPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/orgs-hotels"
          element={
            <ProtectedRoute
              isAuthenticated={isAuthenticated}
              userRole={user?.role}
              allowedRoles={['SUPERADMIN']}
            >
              <Layout user={user} onLogout={handleLogout}>
                <AdminOrgsHotelsPage />
              </Layout>
            </ProtectedRoute>
          }
        />

        {/* Root redirect */}
        <Route
          path="/"
          element={
            isAuthenticated ? (
              user?.role === 'GERENTE' || user?.role === 'SUPERADMIN' ? (
                <Navigate to="/overview" replace />
              ) : (
                <Navigate to="/tickets" replace />
              )
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
