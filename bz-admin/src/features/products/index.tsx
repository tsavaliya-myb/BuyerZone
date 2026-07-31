import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  Package, Search, Plus, ChevronLeft, ChevronRight, AlertTriangle,
  Trash2, Edit2, X, ImageOff, Loader2,
} from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import {
  inhouseProductsService,
  type InHouseProduct,
} from '@/services/inhouseProducts';
import { useUIStore } from '@/store/uiStore';

const PAGE_SIZE = 20;

interface PhotoDraft {
  file: File;
  previewUrl: string;
}

export default function Products() {
  const { showToast, openAddProductModal } = useUIStore();

  const [products, setProducts] = useState<InHouseProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');

  const [editModal, setEditModal] = useState<{
    isOpen: boolean;
    product: InHouseProduct | null;
    name: string;
    price: string;
    keywords: string;
    newPhotos: PhotoDraft[];
    isLoading: boolean;
    error: string;
  }>({ isOpen: false, product: null, name: '', price: '', keywords: '', newPhotos: [], isLoading: false, error: '' });

  const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; product: InHouseProduct | null; isLoading: boolean }>({
    isOpen: false, product: null, isLoading: false,
  });

  const fetchProducts = async (targetPage = page, targetKeyword = keyword) => {
    try {
      setLoading(true);
      const data = await inhouseProductsService.list({
        page: targetPage, page_size: PAGE_SIZE, keyword: targetKeyword || undefined,
      });
      setProducts(data.items);
      setTotal(data.total);
      setPage(data.page);
    } catch (error) {
      console.error('Failed to fetch in-house products', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts(1, keyword);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    fetchProducts(1, keyword);
  };

  // ── Edit ───────────────────────────────────────────────────────────────

  const openEditModal = (product: InHouseProduct) => {
    setEditModal({
      isOpen: true,
      product,
      name: product.name,
      price: String(product.price),
      keywords: product.keywords.join(', '),
      newPhotos: [],
      isLoading: false,
      error: '',
    });
  };

  const handleEditPhotosChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const drafts = files.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }));
    setEditModal((prev) => ({ ...prev, newPhotos: [...prev.newPhotos, ...drafts] }));
  };

  const removeEditDraftPhoto = (index: number) => {
    setEditModal((prev) => ({ ...prev, newPhotos: prev.newPhotos.filter((_, i) => i !== index) }));
  };

  const handleRemoveExistingPhoto = async (photoId: string) => {
    if (!editModal.product) return;
    try {
      const updated = await inhouseProductsService.removePhoto(editModal.product.id, photoId);
      setEditModal((prev) => ({ ...prev, product: updated }));
    } catch (err) {
      console.error('Failed to remove photo', err);
      showToast('Failed to remove photo', 'error');
    }
  };

  const handleEditSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!editModal.product) return;
    const price = parseFloat(editModal.price);
    if (!editModal.name.trim() || !price || price <= 0) {
      setEditModal((prev) => ({ ...prev, error: 'Name and a valid price are required' }));
      return;
    }

    setEditModal((prev) => ({ ...prev, isLoading: true, error: '' }));
    try {
      await inhouseProductsService.update(editModal.product.id, {
        name: editModal.name.trim(),
        price,
        keywords: editModal.keywords.split(',').map((k) => k.trim()).filter(Boolean),
      });
      if (editModal.newPhotos.length > 0) {
        await inhouseProductsService.addPhotos(editModal.product.id, editModal.newPhotos.map((p) => p.file));
      }
      showToast('Product updated', 'success');
      setEditModal((prev) => ({ ...prev, isOpen: false }));
      fetchProducts(page, keyword);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Failed to update product';
      setEditModal((prev) => ({ ...prev, isLoading: false, error: typeof msg === 'string' ? msg : 'Failed to update product' }));
    }
  };

  // ── Delete ─────────────────────────────────────────────────────────────

  const handleDelete = async () => {
    if (!deleteModal.product) return;
    setDeleteModal((prev) => ({ ...prev, isLoading: true }));
    try {
      await inhouseProductsService.remove(deleteModal.product.id);
      setDeleteModal({ isOpen: false, product: null, isLoading: false });
      fetchProducts(page, keyword);
    } catch (err) {
      console.error('Failed to delete product', err);
      setDeleteModal((prev) => ({ ...prev, isLoading: false }));
      showToast('Failed to delete product', 'error');
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <MainLayout>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-800 tracking-tight">Products</h1>
          <p className="text-sm text-slate-400 font-medium mt-1">Manage in-house products — name, price, photos and search keywords.</p>
        </div>
        <button
          onClick={() => openAddProductModal(() => fetchProducts(1, keyword))}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-bold hover:bg-primary-dark transition-all shadow-lg shadow-primary/20"
        >
          <Plus size={16} /> Add Product
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="card bg-white p-6 shadow-sm border border-slate-50 flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Package size={24} />
          </div>
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">TOTAL PRODUCTS</p>
            <h3 className="text-2xl font-black text-slate-800 tracking-tight">{loading ? '...' : total.toLocaleString()}</h3>
          </div>
        </div>
      </div>

      <div className="card bg-white overflow-hidden shadow-sm border border-slate-50">
        <form onSubmit={handleSearch} className="p-6 border-b border-slate-50 flex flex-col md:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Search by name or keyword..."
              className="w-full pl-12 pr-4 py-3 bg-slate-50 border-none rounded-xl text-sm font-medium focus:ring-2 focus:ring-primary/20 transition-all outline-none"
            />
          </div>
          <button type="submit" className="btn btn-primary px-6 rounded-xl text-xs font-bold">
            Search
          </button>
        </form>

        <div className="overflow-x-auto">
          <table className="w-full text-left min-w-[900px]">
            <thead>
              <tr className="bg-[#fcfdff] border-b border-slate-50 uppercase text-[9px] font-bold text-slate-400 tracking-widest">
                <th className="px-8 py-5">Product</th>
                <th className="px-8 py-5">Price</th>
                <th className="px-8 py-5">Keywords</th>
                <th className="px-8 py-5">Status</th>
                <th className="px-8 py-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50 text-sm">
              {loading ? (
                <tr><td colSpan={5} className="px-8 py-10 text-center text-slate-500 font-medium">Loading products...</td></tr>
              ) : products.length === 0 ? (
                <tr><td colSpan={5} className="px-8 py-10 text-center text-slate-500 font-medium">No products found.</td></tr>
              ) : products.map((product) => {
                const thumb = product.photos[0]?.url;
                return (
                  <tr key={product.id} className="hover:bg-slate-50/50 transition-colors group">
                    <td className="px-8 py-5">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-slate-100 overflow-hidden border border-slate-100 flex items-center justify-center flex-shrink-0">
                          {thumb ? (
                            <img src={thumb} alt={product.name} className="w-full h-full object-cover" />
                          ) : (
                            <ImageOff size={18} className="text-slate-300" />
                          )}
                        </div>
                        <div>
                          <h4 className="font-bold text-slate-800 leading-none">{product.name}</h4>
                          <p className="text-[10px] font-bold text-slate-400 mt-1 uppercase tracking-wider">{product.photos.length} photo{product.photos.length !== 1 ? 's' : ''}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-8 py-5 font-semibold text-slate-600">₹{product.price.toLocaleString()}</td>
                    <td className="px-8 py-5">
                      <div className="flex flex-wrap gap-1.5 max-w-[240px]">
                        {product.keywords.slice(0, 3).map((kw) => (
                          <span key={kw} className="px-2.5 py-1 bg-slate-100 text-slate-600 rounded-full text-[10px] font-bold">{kw}</span>
                        ))}
                        {product.keywords.length > 3 && (
                          <span className="px-2.5 py-1 bg-slate-50 text-slate-400 rounded-full text-[10px] font-bold">+{product.keywords.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-8 py-5">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${product.status === 'active' ? 'bg-blue-500' : 'bg-slate-300'}`}></span>
                        <span className={`text-[11px] font-bold ${product.status === 'active' ? 'text-blue-600' : 'text-slate-400'}`}>
                          {product.status === 'active' ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </td>
                    <td className="px-8 py-5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openEditModal(product)}
                          className="text-slate-300 hover:text-primary transition-all p-2 hover:bg-slate-50 rounded-lg active:scale-90"
                          title="Edit Product"
                        >
                          <Edit2 size={18} />
                        </button>
                        <button
                          onClick={() => setDeleteModal({ isOpen: true, product, isLoading: false })}
                          className="text-slate-300 hover:text-red-500 transition-all p-2 hover:bg-red-50 rounded-lg active:scale-90"
                          title="Delete Product"
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
          <p className="text-[11px] font-bold text-slate-400">Showing {products.length} of {total} products</p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchProducts(page - 1, keyword)}
              disabled={page <= 1 || loading}
              className="w-8 h-8 flex items-center justify-center rounded-xl border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors disabled:opacity-40"
            >
              <ChevronLeft size={16} />
            </button>
            <button className="w-8 h-8 flex items-center justify-center rounded-xl bg-primary text-white text-xs font-bold">{page}</button>
            <button
              onClick={() => fetchProducts(page + 1, keyword)}
              disabled={page >= totalPages || loading}
              className="w-8 h-8 flex items-center justify-center rounded-xl border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors disabled:opacity-40"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Edit Modal */}
      {editModal.isOpen && editModal.product && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
            onClick={() => !editModal.isLoading && setEditModal((prev) => ({ ...prev, isOpen: false }))}
          />
          <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-lg relative animate-scale-in overflow-hidden max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 sticky top-0">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                  <Edit2 size={20} />
                </div>
                <h2 className="text-xl font-bold text-slate-800">Edit Product</h2>
              </div>
              <button
                onClick={() => !editModal.isLoading && setEditModal((prev) => ({ ...prev, isOpen: false }))}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
                disabled={editModal.isLoading}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="p-8 space-y-5">
              {editModal.error && (
                <div className="p-3 bg-red-50 text-red-600 text-sm rounded-xl border border-red-100">{editModal.error}</div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
                <input
                  type="text"
                  value={editModal.name}
                  onChange={(e) => setEditModal((prev) => ({ ...prev, name: e.target.value }))}
                  className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
                  required
                  disabled={editModal.isLoading}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Price (₹)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={editModal.price}
                  onChange={(e) => setEditModal((prev) => ({ ...prev, price: e.target.value }))}
                  className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
                  required
                  disabled={editModal.isLoading}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Keywords</label>
                <input
                  type="text"
                  value={editModal.keywords}
                  onChange={(e) => setEditModal((prev) => ({ ...prev, keywords: e.target.value }))}
                  className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
                  disabled={editModal.isLoading}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
                <select
                  value={editModal.product.status}
                  onChange={(e) => setEditModal((prev) => prev.product ? ({ ...prev, product: { ...prev.product, status: e.target.value } }) : prev)}
                  className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
                  disabled={editModal.isLoading}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Existing Photos</label>
                <div className="grid grid-cols-4 gap-2 mb-3">
                  {editModal.product.photos.map((photo) => (
                    <div key={photo.id} className="relative aspect-square rounded-lg overflow-hidden border border-slate-100 group">
                      <img src={photo.url} alt="" className="w-full h-full object-cover" />
                      <button
                        type="button"
                        onClick={() => handleRemoveExistingPhoto(photo.id)}
                        className="absolute top-1 right-1 w-5 h-5 bg-slate-900/70 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                  {editModal.product.photos.length === 0 && (
                    <p className="text-xs text-slate-400 col-span-4">No photos yet.</p>
                  )}
                </div>

                <label className="block text-sm font-medium text-slate-700 mb-2">Add Photos</label>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={handleEditPhotosChange}
                  className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-primary-light file:text-primary hover:file:bg-primary/20"
                  disabled={editModal.isLoading}
                />
                {editModal.newPhotos.length > 0 && (
                  <div className="grid grid-cols-4 gap-2 mt-3">
                    {editModal.newPhotos.map((photo, i) => (
                      <div key={i} className="relative aspect-square rounded-lg overflow-hidden border border-slate-100 group">
                        <img src={photo.previewUrl} alt="" className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => removeEditDraftPhoto(i)}
                          className="absolute top-1 right-1 w-5 h-5 bg-slate-900/70 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setEditModal((prev) => ({ ...prev, isOpen: false }))}
                  disabled={editModal.isLoading}
                  className="flex-1 px-6 py-4 rounded-2xl bg-slate-50 text-slate-600 font-bold hover:bg-slate-100 transition-all active:scale-95 text-[10px] uppercase tracking-widest disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editModal.isLoading}
                  className="flex-[1.5] px-6 py-4 rounded-2xl text-white font-bold transition-all shadow-lg active:scale-95 text-[10px] uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 bg-primary hover:bg-primary-dark shadow-primary/20"
                >
                  {editModal.isLoading ? (
                    <><Loader2 size={16} className="animate-spin" /> Saving...</>
                  ) : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteModal.isOpen && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
            onClick={() => !deleteModal.isLoading && setDeleteModal({ ...deleteModal, isOpen: false })}
          />
          <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-md relative animate-scale-in overflow-hidden">
            <div className="p-8 flex flex-col items-center text-center">
              <div className="w-20 h-20 rounded-3xl flex items-center justify-center mb-6 bg-red-50 text-red-500">
                <AlertTriangle size={40} />
              </div>
              <h3 className="text-2xl font-black text-slate-800 tracking-tight mb-2">Delete Product?</h3>
              <p className="text-slate-500 font-medium leading-relaxed mb-8">
                Are you sure you want to delete {deleteModal.product?.name}? This also removes all its photos permanently.
              </p>
              <div className="flex gap-3 w-full">
                <button
                  onClick={() => setDeleteModal({ ...deleteModal, isOpen: false })}
                  disabled={deleteModal.isLoading}
                  className="flex-1 px-6 py-4 rounded-2xl bg-slate-50 text-slate-600 font-bold hover:bg-slate-100 transition-all active:scale-95 text-[10px] uppercase tracking-widest disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleteModal.isLoading}
                  className="flex-[1.5] px-6 py-4 rounded-2xl text-white font-bold transition-all shadow-lg active:scale-95 text-[10px] uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 bg-red-500 hover:bg-red-600 shadow-red-200"
                >
                  {deleteModal.isLoading ? (
                    <><Loader2 size={16} className="animate-spin" /> Deleting...</>
                  ) : 'Delete Now'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </MainLayout>
  );
}
