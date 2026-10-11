import React from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { DatasetProvider } from './context/DatasetContext';
import { HomePage } from './pages/HomePage';
import { DashboardPage } from './pages/DashboardPage';
import { LoginPage } from './pages/LoginPage';

const Protected = ({ children }) => {
  const { token, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return null;
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
};

export function App() {
  return (
    <AuthProvider>
      <DatasetProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<Protected><HomePage /></Protected>} />
            <Route path="/insights" element={<Protected><DashboardPage /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </DatasetProvider>
    </AuthProvider>
  );
}

export default App;
