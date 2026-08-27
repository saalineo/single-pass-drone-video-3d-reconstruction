import { Link, Outlet } from 'react-router-dom';

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="border-b border-slate-200 bg-white px-4 py-3 md:px-6">
        <Link to="/" className="text-sm font-semibold text-slate-800">
          Operator Console
        </Link>
      </nav>
      <Outlet />
    </div>
  );
}
