import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth";
import { useAuth } from "./lib/auth";
import { AuthProvider } from "./lib/auth-context";
import { ClaimDetailPage } from "./pages/ClaimDetailPage";
import { ClaimsPage } from "./pages/ClaimsPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";

function HomeRedirect() {
  const { token } = useAuth();
  return <Navigate to={token ? "/claims" : "/login"} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/claims"
            element={
              <RequireAuth>
                <ClaimsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/claims/:id"
            element={
              <RequireAuth>
                <ClaimDetailPage />
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
