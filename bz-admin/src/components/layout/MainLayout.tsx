import { type ReactNode } from 'react';
import Sidebar from './Sidebar';
import Navbar from './Navbar';
import SettingsDrawer from './SettingsDrawer';
import ProductDetailModal from '../modals/ProductDetailModal';
import AddSellerModal from '../modals/AddSellerModal';
import AddInHouseProductModal from '../modals/AddInHouseProductModal';
import TelegramConnectModal from '../messaging/TelegramConnectModal';
import WhatsappConnectModal from '../messaging/WhatsappConnectModal';
import { useUIStore } from '@/store/uiStore';
import { X } from 'lucide-react';

interface MainLayoutProps {
  children: ReactNode;
}

export default function MainLayout({ children }: MainLayoutProps) {
  const { 
    isMobileSidebarOpen, 
    closeMobileSidebar,
    isTelegramModalOpen,
    closeTelegramModal,
    isWhatsappModalOpen,
    closeWhatsappModal
  } = useUIStore();

  return (
    <div className="flex min-h-screen bg-[#f4f7fe]">
      {/* Sidebar - Desktop */}
      <div className="hidden lg:block w-72 h-screen fixed left-0 top-0 border-r border-slate-200 bg-white">
        <Sidebar />
      </div>

      {/* Sidebar - Mobile Drawer */}
      <div
        className={`lg:hidden fixed inset-0 z-[100] transition-visibility duration-300 ${isMobileSidebarOpen ? 'visible' : 'invisible'}`}
      >
        {/* Backdrop */}
        <div
          className={`absolute inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity duration-300 ${isMobileSidebarOpen ? 'opacity-100' : 'opacity-0'}`}
          onClick={closeMobileSidebar}
        />

        {/* Sidebar Content */}
        <div
          className={`absolute left-0 top-0 bottom-0 w-72 bg-white shadow-2xl transition-transform duration-300 ease-in-out ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
        >
          <div className="p-4 flex justify-between items-center border-b border-slate-50">
            <h2 className="font-bold text-primary text-xl">BuyerZone</h2>
            <button onClick={closeMobileSidebar} className="p-2 text-slate-400">
              <X size={24} />
            </button>
          </div>
          <Sidebar />
        </div>
      </div>

      {/* Main Content Area */}
      <div className={`flex-1 min-w-0 ${isMobileSidebarOpen ? 'overflow-hidden lg:overflow-auto' : ''} lg:ml-72 flex flex-col`}>
        {/* Navbar */}
        <Navbar />

        {/* Dynamic Page Content */}
        <main className="p-4 md:pt-6 md:pb-8 md:px-8 max-w-[1600px] w-full mx-auto">
          {children}
        </main>

        {/* Footer */}
        <footer className="mt-auto py-6 text-center text-xs text-slate-400 font-medium uppercase tracking-widest px-4">
          © 2026 BUYERZONE | AI AUTOMATION
        </footer>
      </div>

      {/* Overlays */}
      <SettingsDrawer />
      <ProductDetailModal />
      <AddSellerModal />
      <AddInHouseProductModal />
      
      {/* Messaging Overlays */}
      <TelegramConnectModal 
        isOpen={isTelegramModalOpen} 
        onClose={closeTelegramModal} 
      />
      <WhatsappConnectModal 
        isOpen={isWhatsappModalOpen} 
        onClose={closeWhatsappModal} 
      />
    </div>
  );
}
