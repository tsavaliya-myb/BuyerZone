import { LayoutDashboard, Image, Users, Package, LogOut } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useUIStore } from '@/store/uiStore';
import { authService } from '@/services/auth';

const menuItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
  { icon: Image, label: 'Image Search', path: '/image-search' },
  // { icon: BarChart3, label: 'Analysis', path: '/analysis' },
  { icon: Users, label: 'Sellers', path: '/sellers' },
  { icon: Package, label: 'Products', path: '/products' },
  // { icon: Download, label: 'Export', path: '/export' },
];

export default function Sidebar() {
  const { closeMobileSidebar } = useUIStore();

  const handleLinkClick = () => {
    closeMobileSidebar();
  };

  return (
    <div className="flex flex-col h-full p-6">
      {/* Logo */}
      <div className="flex items-center gap-3 mb-8 px-2">
        <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center text-white">
          <LayoutDashboard size={24} />
        </div>
        <div>
          <h1 className="font-bold text-lg leading-tight tracking-tight">BuyerZone</h1>
          <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Wholesale Analysis</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-2">
        {menuItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.path}
            onClick={handleLinkClick}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <item.icon size={20} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Bottom Actions */}
      <div className="pt-6 border-t border-slate-100 space-y-2">
        {/* <button 
          onClick={() => {
            openSettings();
            handleLinkClick();
          }}
          className="nav-item w-full text-left"
        >
          <Settings size={20} />
          <span>Settings</span>
        </button>
        <button className="nav-item w-full text-left" onClick={handleLinkClick}>
          <HelpCircle size={20} />
          <span>Help</span>
        </button> */}
        <button
          className="nav-item w-full text-left text-red-600 hover:bg-red-50 hover:text-red-700"
          onClick={() => {
            authService.logout();
            handleLinkClick();
          }}
        >
          <LogOut size={20} />
          <span>Logout</span>
        </button>
      </div>
    </div>
  );
}
