import { Home, MessageCircle, Users, Settings, ShieldCheck, ShoppingBag, Zap, Calendar, BarChart3, Ear, UserSearch, FileText } from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';

const mainNav = [
  { path: '/new/inicio', icon: Home, label: 'Inicio' },
  { path: '/new/mensajes', icon: MessageCircle, label: 'Mensajes' },
  { path: '/new/clientes', icon: Users, label: 'Clientes' },
  { path: '/new/ajustes', icon: Settings, label: 'Ajustes' },
];

const toolsNav = [
  { path: '/new/copilot', icon: ShieldCheck, label: 'Copilot' },
  { path: '/new/products', icon: ShoppingBag, label: 'Productos' },
  { path: '/new/nurturing', icon: Zap, label: 'Nurturing' },
  { path: '/new/bookings', icon: Calendar, label: 'Reservas' },
  { path: '/new/analytics', icon: BarChart3, label: 'Analytics' },
  { path: '/new/audiencia', icon: Ear, label: 'Audiencia' },
  { path: '/new/personas', icon: UserSearch, label: 'Personas' },
];

export function NewNavigation() {
  const location = useLocation();

  return (
    <>
      {/* Mobile: Bottom nav (4 core items) */}
      <nav className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 md:hidden z-50">
        <div className="flex justify-around py-2">
          {mainNav.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex flex-col items-center p-2 ${
                  isActive ? 'text-purple-500' : 'text-gray-400'
                }`
              }
            >
              <item.icon size={24} />
              <span className="text-xs mt-1">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Desktop: Sidebar with main + tools sections */}
      <nav className="hidden md:flex fixed left-0 top-0 bottom-0 w-20 bg-gray-900 border-r border-gray-800 flex-col items-center py-6 gap-2 z-50 overflow-y-auto">
        <div className="text-2xl mb-4">🤖</div>

        {/* Main navigation */}
        {mainNav.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex flex-col items-center p-2 rounded-xl transition-colors ${
                isActive
                  ? 'bg-purple-500/20 text-purple-500'
                  : 'text-gray-400 hover:text-white'
              }`
            }
          >
            <item.icon size={20} />
            <span className="text-[10px] mt-0.5">{item.label}</span>
          </NavLink>
        ))}

        {/* Separator */}
        <div className="w-10 border-t border-gray-700 my-2" />

        {/* Tools navigation */}
        {toolsNav.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex flex-col items-center p-2 rounded-xl transition-colors ${
                isActive
                  ? 'bg-purple-500/20 text-purple-500'
                  : 'text-gray-400 hover:text-white'
              }`
            }
          >
            <item.icon size={18} />
            <span className="text-[10px] mt-0.5">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
}
