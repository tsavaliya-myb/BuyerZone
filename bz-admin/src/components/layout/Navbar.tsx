import { useState } from 'react';
import { Menu, Send, MessageCircle } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';

export default function Navbar() {
  const { openMobileSidebar, openTelegramModal, openWhatsappModal } = useUIStore();
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);

  // Get dynamic name from login data or JWT token
  const token = localStorage.getItem('token');
  let displayName = 'User';
  if (token) {
    const storedName = localStorage.getItem('user_name') || localStorage.getItem('username');
    if (storedName) {
      displayName = storedName;
    } else {
      try {
        const base64Url = token.split('.')[1];
        if (base64Url) {
          const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
          const jsonPayload = decodeURIComponent(
            atob(base64)
              .split('')
              .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
              .join('')
          );
          const payload = JSON.parse(jsonPayload);
          displayName = payload.name || payload.username || payload.sub || 'User';
        }
      } catch (e) {
        console.error('Error decoding token', e);
      }
    }
  }

  return (
    <header className="h-20 bg-white/80 backdrop-blur-md sticky top-0 z-10 px-4 md:px-8 flex items-center justify-between border-b border-slate-100">
      {/* Mobile Logo & Menu */}
      <div className="lg:hidden flex items-center gap-2">
        <button
          onClick={openMobileSidebar}
          className="p-2 -ml-2 text-slate-500 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <Menu size={24} />
        </button>
        <h1 className="font-bold text-primary text-xl">BuyerZone</h1>
      </div>

      {/* Right Side Actions */}
      <div className="flex items-center gap-4 ml-auto">
        {/* User Profile with Dropdown */}
        <div className="relative">
          <button
            onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
            className="flex items-center gap-3 pl-2 cursor-pointer hover:opacity-80 transition-opacity focus:outline-none text-left"
          >
            <div className="text-right hidden sm:block">
              <h4 className="text-sm font-bold text-slate-800 leading-none">{displayName}</h4>
              <p className="text-[10px] font-bold text-slate-400 uppercase mt-1">Head of Procurement</p>
            </div>
            <div className="w-10 h-10 rounded-full overflow-hidden border-2 border-primary-light flex-shrink-0">
              <img
                src={`https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=0D8ABC&color=fff`}
                alt={displayName}
                className="w-full h-full object-cover"
              />
            </div>
          </button>

          {/* Profile Menu Dropdown */}
          {isProfileMenuOpen && (
            <>
              {/* Backdrop to close dropdown on click outside */}
              <div
                className="fixed inset-0 z-10"
                onClick={() => setIsProfileMenuOpen(false)}
              />
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-2xl border border-slate-100 shadow-xl py-2 z-20 animate-in fade-in slide-in-from-top-2 duration-200">
                <div className="px-4 py-2 border-b border-slate-50">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Connections</p>
                </div>

                <button
                  onClick={() => {
                    openTelegramModal();
                    setIsProfileMenuOpen(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-700 hover:bg-slate-50 transition-colors text-left"
                >
                  <Send className="w-4 h-4 text-[#0088cc]" />
                  <span className="font-medium">Telegram Connect</span>
                </button>

                <button
                  onClick={() => {
                    openWhatsappModal();
                    setIsProfileMenuOpen(false);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-700 hover:bg-slate-50 transition-colors text-left"
                >
                  <MessageCircle className="w-4 h-4 text-[#25D366]" />
                  <span className="font-medium">WhatsApp Connect</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
