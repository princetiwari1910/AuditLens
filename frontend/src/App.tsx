import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Home from './pages/Home';
import Capture from './pages/Capture';
import Processing from './pages/Processing';
import Report from './pages/Report';
import Compare from './pages/Compare';
import EvalDashboard from './pages/EvalDashboard';
import SitesPage from './pages/SitesPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/new/:templateId" element={<Capture />} />
          <Route path="/audits/:id/processing" element={<Processing />} />
          <Route path="/audits/:id" element={<Report />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/eval" element={<EvalDashboard />} />
          <Route path="/sites" element={<SitesPage />} />
          <Route path="/sites/:id" element={<SitesPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
