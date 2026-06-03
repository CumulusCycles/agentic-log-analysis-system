import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth";
import { useAuth } from "./lib/auth";
import { AuthProvider } from "./lib/auth-context";
import { ClaimsPage } from "./pages/ClaimsPage";
import { LoginPage } from "./pages/LoginPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { ProfilePage } from "./pages/ProfilePage";

function HomeRedirect() {
  const { token } = useAuth();
  return <Navigate to={token ? "/policies" : "/login"} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/policies"
            element={
              <RequireAuth>
                <PoliciesPage />
              </RequireAuth>
            }
          />
          <Route
            path="/claims"
            element={
              <RequireAuth>
                <ClaimsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/profile"
            element={
              <RequireAuth>
                <ProfilePage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
