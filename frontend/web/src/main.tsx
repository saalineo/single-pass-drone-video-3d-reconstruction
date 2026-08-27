import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { Ion } from 'cesium';
import { router } from './router';
import { ToastProvider } from './components/Toast/ToastProvider';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import './styles/index.css';

Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN ?? '';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 2 } },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <ToastProvider />
    </QueryClientProvider>
  </React.StrictMode>,
);
