import { useEffect, useState } from 'react';
import { Users, Package, Search, Plus, ChevronLeft, ChevronRight, AlertTriangle, Trash2, Edit2, X } from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import { sellersService, type Seller } from '@/services/sellers';
import { useUIStore } from '@/store/uiStore';

export default function Sellers() {
  const { openAddSellerModal } = useUIStore();
  const [sellers, setSellers] = useState<Seller[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    seller: Seller | null;
    isLoading: boolean;
  }>({
    isOpen: false,
    seller: null,
    isLoading: false,
  });

  const [updatePhoneModal, setUpdatePhoneModal] = useState<{
    isOpen: boolean;
    seller: Seller | null;
    phone: string;
    isLoading: boolean;
    error: string;
  }>({
    isOpen: false,
    seller: null,
    phone: '',
    isLoading: false,
    error: '',
  });

  const handleOpenUpdatePhone = (seller: Seller) => {
    setUpdatePhoneModal({
      isOpen: true,
      seller,
      phone: seller.phone || '',
      isLoading: false,
      error: '',
    });
  };

  const formatPhoneNumber = (input: string) => {
    const cleaned = input.replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `91${cleaned}`;
    }
    return cleaned;
  };

  const handleUpdatePhoneSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!updatePhoneModal.seller) return;
    
    setUpdatePhoneModal(prev => ({ ...prev, isLoading: true, error: '' }));
    try {
      const formattedPhone = formatPhoneNumber(updatePhoneModal.phone);
      await sellersService.updateSellerPhone(updatePhoneModal.seller.id, formattedPhone);
      fetchSellers();
      setUpdatePhoneModal({ isOpen: false, seller: null, phone: '', isLoading: false, error: '' });
    } catch (err: any) {
      console.error("Failed to update phone number", err);
      setUpdatePhoneModal(prev => ({ ...prev, isLoading: false, error: err.response?.data?.message || err.message || 'Failed to update phone number' }));
    }
  };

  const fetchSellers = async () => {
    try {
      setLoading(true);
      const data = await sellersService.getSellers();
      setSellers(data.filter(seller => seller.is_active));
    } catch (error) {
      console.error("Failed to fetch sellers", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSellers();
  }, []);

  const handleToggleStatus = (seller: Seller) => {
    setConfirmModal({
      isOpen: true,
      seller,
      isLoading: false,
    });
  };

  const executeToggleStatus = async () => {
    if (!confirmModal.seller) return;
    
    const { seller } = confirmModal;
    setConfirmModal(prev => ({ ...prev, isLoading: true }));
    
    try {
      if (seller.is_active) {
        await sellersService.deactivateSeller(seller.id);
      } else {
        await sellersService.addSeller(seller.chat_name);
      }
      fetchSellers();
      setConfirmModal({ isOpen: false, seller: null, isLoading: false });
    } catch (error) {
      console.error(`Failed to toggle seller status`, error);
      setConfirmModal(prev => ({ ...prev, isLoading: false }));
    }
  };

  const totalSellers = sellers.length;
  const totalProducts = sellers.reduce((acc, curr) => acc + (curr.product_count || 0), 0);

  const getColor = (index: number) => {
    const colors = ['bg-blue-100 text-blue-600', 'bg-purple-100 text-purple-600', 'bg-emerald-100 text-emerald-600', 'bg-amber-100 text-amber-600'];
    return colors[index % colors.length];
  };

  return (
    <MainLayout>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-800 tracking-tight">Seller Management</h1>
          <p className="text-sm text-slate-400 font-medium mt-1">Manage your wholesale distribution network. Monitor inventory volume and contact details.</p>
        </div>
        <div className="flex items-center gap-3">
          {/* <button className="flex items-center gap-2 px-4 py-2.5 bg-white text-slate-600 border border-slate-200 rounded-xl text-xs font-bold hover:bg-slate-50 transition-colors">
            <Filter size={16} /> Advanced Filters
          </button> */}
          <button
            onClick={() => openAddSellerModal(fetchSellers)}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-bold hover:bg-primary-dark transition-all shadow-lg shadow-primary/20"
          >
            <Plus size={16} /> Add New Seller
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {[
          { icon: Users, label: 'TOTAL SELLERS', value: loading ? '...' : totalSellers.toLocaleString(), color: 'bg-blue-50 text-blue-600' },
          { icon: Package, label: 'TOTAL PRODUCTS', value: loading ? '...' : totalProducts.toLocaleString(), color: 'bg-indigo-50 text-indigo-600' },
        ].map((stat, i) => (
          <div key={i} className="card bg-white p-6 shadow-sm border border-slate-50 flex items-center gap-4">
            <div className={`w-14 h-14 rounded-2xl ${stat.color} flex items-center justify-center`}>
              <stat.icon size={24} />
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{stat.label}</p>
              <h3 className="text-2xl font-black text-slate-800 tracking-tight">{stat.value}</h3>
            </div>
          </div>
        ))}
      </div>

      <div className="card bg-white overflow-hidden shadow-sm border border-slate-50">
        <div className="p-6 border-b border-slate-50 flex flex-col md:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              placeholder="Search by name, ID, or phone..."
              className="w-full pl-12 pr-4 py-3 bg-slate-50 border-none rounded-xl text-sm font-medium focus:ring-2 focus:ring-primary/20 transition-all outline-none"
            />
          </div>
          <div className="flex items-center gap-3">
            <select className="bg-slate-50 border-none rounded-xl px-4 py-3 text-sm font-bold text-slate-600 outline-none cursor-pointer">
              <option>All Categories</option>
            </select>
            <select className="bg-slate-50 border-none rounded-xl px-4 py-3 text-sm font-bold text-slate-600 outline-none cursor-pointer">
              <option>High Volume</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left min-w-[900px]">
            <thead>
              <tr className="bg-[#fcfdff] border-b border-slate-50 uppercase text-[9px] font-bold text-slate-400 tracking-widest">
                <th className="px-8 py-5">Seller Name</th>
                <th className="px-8 py-5">Phone Number</th>
                <th className="px-8 py-5">Category</th>
                <th className="px-8 py-5">Total Products Sent</th>
                <th className="px-8 py-5">Status</th>
                <th className="px-8 py-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50 text-sm">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-8 py-10 text-center text-slate-500 font-medium">Loading sellers...</td>
                </tr>
              ) : sellers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-8 py-10 text-center text-slate-500 font-medium">No sellers found.</td>
                </tr>
              ) : sellers.map((seller, i) => {
                const initial = seller.chat_name ? seller.chat_name.substring(0, 2).toUpperCase() : 'NA';
                const statusLabel = seller.is_active ? 'Active' : 'Inactive';
                const progress = Math.min(((seller.product_count || 0) / 1000) * 100, 100);

                return (
                  <tr key={seller.id || i} className="hover:bg-slate-50/50 transition-colors group">
                    <td className="px-8 py-5">
                      <div className="flex items-center gap-4">
                        <div className={`w-9 h-9 rounded-xl ${getColor(i)} flex items-center justify-center text-[11px] font-bold border border-white`}>
                          {initial}
                        </div>
                        <div>
                          <h4 className="font-bold text-slate-800 leading-none">{seller.chat_name}</h4>
                          <p className="text-[10px] font-bold text-slate-400 mt-1 uppercase tracking-wider">ID: {seller.chat_id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-8 py-5 font-semibold text-slate-600">{seller.phone || 'N/A'}</td>
                    <td className="px-8 py-5">
                      <span className="px-3 py-1 bg-slate-100 text-slate-600 rounded-full text-[10px] font-bold uppercase tracking-tight">
                        {seller.chat_type}
                      </span>
                    </td>
                    <td className="px-8 py-5 min-w-[200px]">
                      <div className="flex items-center gap-4">
                        <span className="text-xs font-bold text-slate-700">{(seller.product_count || 0).toLocaleString()}</span>
                        <div className="flex-1 h-1.5 bg-slate-50 rounded-full overflow-hidden">
                          <div className="h-full bg-primary rounded-full transition-all duration-1000" style={{ width: `${progress}%` }}></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-8 py-5">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${seller.is_active ? 'bg-blue-500' : 'bg-slate-300'}`}></span>
                        <span className={`text-[11px] font-bold ${seller.is_active ? 'text-blue-600' : 'text-slate-400'}`}>{statusLabel}</span>
                      </div>
                    </td>
                    <td className="px-8 py-5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleOpenUpdatePhone(seller)}
                          className="text-slate-300 hover:text-primary transition-all p-2 hover:bg-slate-50 rounded-lg active:scale-90"
                          title="Update Phone Number"
                        >
                          <Edit2 size={18} />
                        </button>
                        <button
                          onClick={() => handleToggleStatus(seller)}
                          className="text-slate-300 hover:text-red-500 transition-all p-2 hover:bg-red-50 rounded-lg active:scale-90"
                          title="Delete Seller"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="p-6 border-t border-slate-50 flex items-center justify-between">
          <p className="text-[11px] font-bold text-slate-400">Showing {sellers.length} of {totalSellers} sellers</p>
          <div className="flex items-center gap-2">
            <button className="w-8 h-8 flex items-center justify-center rounded-xl border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors">
              <ChevronLeft size={16} />
            </button>
            <button className="w-8 h-8 flex items-center justify-center rounded-xl bg-primary text-white text-xs font-bold">1</button>
            <button className="w-8 h-8 flex items-center justify-center rounded-xl border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
      {/* Custom Update Phone Modal */}
      {updatePhoneModal.isOpen && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in" 
            onClick={() => !updatePhoneModal.isLoading && setUpdatePhoneModal({ ...updatePhoneModal, isOpen: false })} 
          />
          <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-md relative animate-scale-in overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                  <Edit2 size={20} />
                </div>
                <h2 className="text-xl font-bold text-slate-800">Update Phone Number</h2>
              </div>
              <button
                onClick={() => !updatePhoneModal.isLoading && setUpdatePhoneModal({ ...updatePhoneModal, isOpen: false })}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
                disabled={updatePhoneModal.isLoading}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleUpdatePhoneSubmit} className="p-8 space-y-6">
              {updatePhoneModal.error && (
                <div className="p-3 bg-red-50 text-red-600 text-sm rounded-xl border border-red-100">
                  {updatePhoneModal.error}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Phone Number for {updatePhoneModal.seller?.chat_name}</label>
                <input
                  type="text"
                  value={updatePhoneModal.phone}
                  onChange={(e) => setUpdatePhoneModal({ ...updatePhoneModal, phone: e.target.value })}
                  placeholder="Enter phone number (e.g. 9876543210)"
                  className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
                  required
                  disabled={updatePhoneModal.isLoading}
                />
                <p className="text-[10px] text-slate-400 mt-1">If you enter a 10-digit number, India country code (91) will be auto-prepended.</p>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setUpdatePhoneModal({ ...updatePhoneModal, isOpen: false })}
                  disabled={updatePhoneModal.isLoading}
                  className="flex-1 px-6 py-4 rounded-2xl bg-slate-50 text-slate-600 font-bold hover:bg-slate-100 transition-all active:scale-95 text-[10px] uppercase tracking-widest disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updatePhoneModal.isLoading}
                  className="flex-[1.5] px-6 py-4 rounded-2xl text-white font-bold transition-all shadow-lg active:scale-95 text-[10px] uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 bg-primary hover:bg-primary-dark shadow-primary/20"
                >
                  {updatePhoneModal.isLoading ? (
                    <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Updating...</>
                  ) : (
                    'Update Now'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Custom Confirmation Modal */}
      {confirmModal.isOpen && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in" 
            onClick={() => !confirmModal.isLoading && setConfirmModal({ ...confirmModal, isOpen: false })} 
          />
          <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-md relative animate-scale-in overflow-hidden">
            <div className="p-8 flex flex-col items-center text-center">
              <div className={`w-20 h-20 rounded-3xl flex items-center justify-center mb-6 ${confirmModal.seller?.is_active ? 'bg-red-50 text-red-500' : 'bg-emerald-50 text-emerald-500'}`}>
                <AlertTriangle size={40} />
              </div>
              
              <h3 className="text-2xl font-black text-slate-800 tracking-tight mb-2">
                Delete Seller?
              </h3>
              
              <p className="text-slate-500 font-medium leading-relaxed mb-8">
                Are you sure you want to delete {confirmModal.seller?.chat_name}? It will no longer be monitored for new products.
              </p>
              
              <div className="flex gap-3 w-full">
                <button
                  onClick={() => setConfirmModal({ ...confirmModal, isOpen: false })}
                  disabled={confirmModal.isLoading}
                  className="flex-1 px-6 py-4 rounded-2xl bg-slate-50 text-slate-600 font-bold hover:bg-slate-100 transition-all active:scale-95 text-[10px] uppercase tracking-widest disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={executeToggleStatus}
                  disabled={confirmModal.isLoading}
                  className="flex-[1.5] px-6 py-4 rounded-2xl text-white font-bold transition-all shadow-lg active:scale-95 text-[10px] uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 bg-red-500 hover:bg-red-600 shadow-red-200"
                >
                  {confirmModal.isLoading ? (
                    <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processing...</>
                  ) : (
                    'Delete Now'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </MainLayout>
  );
}
