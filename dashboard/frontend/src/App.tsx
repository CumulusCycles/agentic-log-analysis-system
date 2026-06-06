import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { useAuth } from "./lib/auth";
import { AuthProvider } from "./lib/auth-context";
import { AiChat } from "./pages/AiChat";
import { ErrorDetail } from "./pages/ErrorDetail";
import { LogGenerator } from "./pages/LogGenerator";
import { LoginPage } from "./pages/LoginPage";
import { LogExplorer } from "./pages/LogExplorer";
import { Overview } from "./pages/Overview";
import { VectorstoreStats } from "./pages/VectorstoreStats";

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
                <Layout>
                  <Overview />
                </Layout>
              </RequireAuth>
            }
          />
          <Route
            path="/logs"
            element={
              <RequireAuth>
                <Layout>
                  <LogExplorer />
                </Layout>
              </RequireAuth>
            }
          />
          <Route
            path="/errors/:id"
            element={
              <RequireAuth>
                <Layout>
                  <ErrorDetail />
                </Layout>
              </RequireAuth>
            }
          />
          <Route
            path="/chat"
            element={
              <RequireAuth>
                <Layout>
                  <AiChat />
                </Layout>
              </RequireAuth>
            }
          />
          <Route
            path="/log-generator"
            element={
              <RequireAuth>
                <Layout>
                  <LogGenerator />
                </Layout>
              </RequireAuth>
            }
          />
          <Route
            path="/vectorstore-stats"
            element={
              <RequireAuth>
                <Layout>
                  <VectorstoreStats />
                </Layout>
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
