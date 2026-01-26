import { Home, MessageCircle, Users, Settings, BarChart3 } from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/new/inicio', icon: Home, label: 'Inicio' },
  { path: '/new/mensajes', icon: MessageCircle, label: 'Mensajes' },
  { path: '/new/clientes', icon: Users, label: 'Clientes' },
  { path: '/analytics', icon: BarChart3, label: 'Analytics' },
  { path: '/new/ajustes', icon: Settings, label: 'Ajustes' },
];

export function NewNavigation() {
  const location = useLocation();

  return (
    <>
      {/* Mobile: Bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 md:hidden z-50">
        <div className="flex justify-around py-2">
          {navItems.map((item) => (
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

      {/* Desktop: Sidebar */}
      <nav className="hidden md:flex fixed left-0 top-0 bottom-0 w-20 bg-gray-900 border-r border-gray-800 flex-col items-center py-6 gap-6 z-50">
        <div className="text-2xl mb-6">🤖</div>
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex flex-col items-center p-3 rounded-xl transition-colors ${
                isActive
                  ? 'bg-purple-500/20 text-purple-500'
                  : 'text-gray-400 hover:text-white'
              }`
            }
          >
            <item.icon size={24} />
            <span className="text-xs mt-1">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
}
