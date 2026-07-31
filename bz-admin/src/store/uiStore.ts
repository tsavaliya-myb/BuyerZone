import { create } from 'zustand';

interface UIState {
  isSettingsOpen: boolean;
  openSettings: () => void;
  closeSettings: () => void;
  toggleSettings: () => void;

  isProductModalOpen: boolean;
  selectedProduct: any;
  openProductModal: (product: any) => void;
  closeProductModal: () => void;

  isMobileSidebarOpen: boolean;
  openMobileSidebar: () => void;
  closeMobileSidebar: () => void;
  toggleMobileSidebar: () => void;

  isAddSellerModalOpen: boolean;
  onSellerAdded: (() => void) | null;
  openAddSellerModal: (onSuccess?: () => void) => void;
  closeAddSellerModal: () => void;

  isAddProductModalOpen: boolean;
  onProductAdded: (() => void) | null;
  openAddProductModal: (onSuccess?: () => void) => void;
  closeAddProductModal: () => void;

  isTelegramModalOpen: boolean;
  openTelegramModal: () => void;
  closeTelegramModal: () => void;

  isWhatsappModalOpen: boolean;
  openWhatsappModal: () => void;
  closeWhatsappModal: () => void;

  toast: {
    message: string;
    type: 'success' | 'error' | 'info';
    isVisible: boolean;
  };
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  hideToast: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isSettingsOpen: false,
  openSettings: () => set({ isSettingsOpen: true }),
  closeSettings: () => set({ isSettingsOpen: false }),
  toggleSettings: () => set((state) => ({ isSettingsOpen: !state.isSettingsOpen })),

  isProductModalOpen: false,
  selectedProduct: null,
  openProductModal: (product) => set({ isProductModalOpen: true, selectedProduct: product }),
  closeProductModal: () => set({ isProductModalOpen: false, selectedProduct: null }),

  isMobileSidebarOpen: false,
  openMobileSidebar: () => set({ isMobileSidebarOpen: true }),
  closeMobileSidebar: () => set({ isMobileSidebarOpen: false }),
  toggleMobileSidebar: () => set((state) => ({ isMobileSidebarOpen: !state.isMobileSidebarOpen })),

  isAddSellerModalOpen: false,
  onSellerAdded: null,
  openAddSellerModal: (onSuccess) => set({ isAddSellerModalOpen: true, onSellerAdded: onSuccess || null }),
  closeAddSellerModal: () => set({ isAddSellerModalOpen: false, onSellerAdded: null }),

  isAddProductModalOpen: false,
  onProductAdded: null,
  openAddProductModal: (onSuccess) => set({ isAddProductModalOpen: true, onProductAdded: onSuccess || null }),
  closeAddProductModal: () => set({ isAddProductModalOpen: false, onProductAdded: null }),

  isTelegramModalOpen: false,
  openTelegramModal: () => set({ isTelegramModalOpen: true }),
  closeTelegramModal: () => set({ isTelegramModalOpen: false }),

  isWhatsappModalOpen: false,
  openWhatsappModal: () => set({ isWhatsappModalOpen: true }),
  closeWhatsappModal: () => set({ isWhatsappModalOpen: false }),

  toast: {
    message: '',
    type: 'info',
    isVisible: false,
  },
  showToast: (message, type = 'info') => {
    set({ toast: { message, type, isVisible: true } });
    // Auto-hide after 4 seconds
    setTimeout(() => {
      set((state) => ({ toast: { ...state.toast, isVisible: false } }));
    }, 4000);
  },
  hideToast: () => set((state) => ({ toast: { ...state.toast, isVisible: false } })),
}));
