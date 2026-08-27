import { createBrowserRouter } from 'react-router-dom';
import App from './App';
import MissionDashboard from './pages/MissionDashboard';
import MissionDetails from './pages/MissionDetails';

export const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      { path: '/', element: <MissionDashboard /> },
      { path: '/missions/:missionId', element: <MissionDetails /> },
    ],
  },
]);
