import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { TicketListPage } from './pages/TicketListPage';
import { TicketDetailPage } from './pages/TicketDetailPage';
import './App.css';

function App() {
  // Mock auth: allow navigation when VITE_USE_MOCKS=true
  const isAuthenticated = import.meta.env.VITE_USE_MOCKS === 'true';
  const user = isAuthenticated
    ? { name: 'Usuario Demo', role: 'RECEPCION' }
    : null;

  const handleLogout = () => {
    // To be implemented in Bloque 2
    alert('Logout - redirigiendo a /login');
    window.location.href = '/login';
  };

  return (
    <BrowserRouter>
      <Routes>
        {/* Login route (public) */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes with Layout */}
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

        {/* Root redirect */}
        <Route
          path="/"
          element={
            isAuthenticated ? (
              <Navigate to="/tickets" replace />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
