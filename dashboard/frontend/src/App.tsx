import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth";
import { useAuth } from "./lib/auth";
import { AuthProvider } from "./lib/auth-context";
import { DashboardHome } from "./pages/DashboardHome";
import { LoginPage } from "./pages/LoginPage";

function HomeRedirect() {
  const { token } = useAuth();
  return <Navigate to={token ? "/" : "/login"} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route
            path="/"
            element={
              <RequireAuth>
                <DashboardHome />
              </RequireAuth>
            }
          />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
