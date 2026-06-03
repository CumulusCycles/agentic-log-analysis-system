import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { RequireAuth } from "./components/RequireAuth";
import { useAuth } from "./lib/auth";
import { AuthProvider } from "./lib/auth-context";
import { ClaimDetailPage } from "./pages/ClaimDetailPage";
import { LoginPage } from "./pages/LoginPage";
import { SubmitClaimPage } from "./pages/SubmitClaimPage";

function HomeRedirect() {
  const { token } = useAuth();
  return <Navigate to={token ? "/submit" : "/login"} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/submit"
            element={
              <RequireAuth>
                <SubmitClaimPage />
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
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
