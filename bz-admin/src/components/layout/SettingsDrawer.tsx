import { X, User, Moon, LogOut } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';
import { authService } from '@/services/auth';

export default function SettingsDrawer() {
  const { isSettingsOpen, closeSettings } = useUIStore();

  if (!isSettingsOpen) return null;

  const handleLogout = () => {
    authService.logout();
  };

  return (
    <div className="fixed inset-0 z-[100] flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
        onClick={closeSettings}
      />

      {/* Drawer Content */}
      <div className={`w-full max-w-md bg-white h-screen shadow-2xl relative flex flex-col transform transition-transform duration-300 ease-out ${isSettingsOpen ? 'translate-x-0' : 'translate-x-full'
        }`}>
        {/* Header */}
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div>
            <h2 className="text-xl font-extrabold text-slate-900 tracking-tight">Settings</h2>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">Configure your environment</p>
          </div>
          <button
            onClick={closeSettings}
            className="p-2 hover:bg-white hover:shadow-md rounded-xl transition-all text-slate-400 hover:text-slate-600 border border-transparent hover:border-slate-100"
          >
            <X size={20} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {/* User Profile Summary */}
          <div className="p-8 border-b border-slate-100 flex flex-col items-center text-center gap-4">
            <div className="relative">
              <div className="w-24 h-24 rounded-3xl overflow-hidden border-4 border-white shadow-xl">
                <img
                  src="https://ui-avatars.com/api/?name=Admin+User&background=0D8ABC&color=fff&size=128"
                  alt="Admin User"
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="absolute -bottom-2 -right-2 w-8 h-8 bg-emerald-500 text-white rounded-xl flex items-center justify-center shadow-lg border-2 border-white">
                <User size={16} />
              </div>
            </div>
            <div className="mt-2">
              <h3 className="text-lg font-black text-slate-900 tracking-tight">Admin User</h3>
              <p className="text-sm font-bold text-slate-400">admin@buyerzone.com</p>
            </div>
          </div>

          <div className="p-6 space-y-6">
            {/* Preferences */}
            <section>
              <h4 className="px-2 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4">Preferences</h4>
              <div className="flex items-center justify-between p-5 bg-slate-50 hover:bg-slate-100 rounded-[24px] transition-all cursor-pointer group border border-transparent hover:border-slate-200">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-2xl bg-white shadow-sm flex items-center justify-center text-slate-500 group-hover:text-primary transition-colors">
                    <Moon size={22} />
                  </div>
                  <div>
                    <p className="text-sm font-black text-slate-800">Dark Mode</p>
                    <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Experimental</p>
                  </div>
                </div>
                <div className="w-12 h-6 bg-slate-300 rounded-full relative cursor-pointer active:scale-95 transition-transform">
                  <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-all shadow-md" />
                </div>
              </div>
            </section>

            {/* Logout */}
            <section className="pt-4">
              <button 
                onClick={handleLogout}
                className="w-full flex items-center gap-4 p-5 hover:bg-red-50 rounded-[24px] transition-all group text-red-600 border border-transparent hover:border-red-100"
              >
                <div className="w-12 h-12 rounded-2xl bg-red-100 flex items-center justify-center text-red-500 group-hover:scale-110 transition-transform">
                  <LogOut size={22} />
                </div>
                <div className="text-left">
                  <p className="text-sm font-black uppercase tracking-tight">Sign Out</p>
                  <p className="text-[11px] font-bold text-red-400 uppercase tracking-widest">End Session</p>
                </div>
              </button>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
