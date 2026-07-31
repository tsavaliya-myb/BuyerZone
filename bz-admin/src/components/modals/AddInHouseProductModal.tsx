import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Plus, X, UploadCloud, Loader2 } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';
import { inhouseProductsService } from '@/services/inhouseProducts';

interface PhotoDraft {
  file: File;
  previewUrl: string;
}

export default function AddInHouseProductModal() {
  const { isAddProductModalOpen, closeAddProductModal, onProductAdded } = useUIStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [keywords, setKeywords] = useState('');
  const [photos, setPhotos] = useState<PhotoDraft[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAddProductModalOpen) {
      setName('');
      setPrice('');
      setKeywords('');
      setPhotos([]);
      setIsLoading(false);
      setError('');
    }
  }, [isAddProductModalOpen]);

  const handlePhotosChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const drafts = files.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }));
    setPhotos((prev) => [...prev, ...drafts]);
  };

  const removePhoto = (index: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const parsedPrice = parseFloat(price);
    if (!name.trim() || !parsedPrice || parsedPrice <= 0) {
      setError('Name and a valid price are required');
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      await inhouseProductsService.create({
        name: name.trim(),
        price: parsedPrice,
        keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean),
        photos: photos.map((p) => p.file),
      });
      if (onProductAdded) onProductAdded();
      closeAddProductModal();
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Failed to create product';
      setIsLoading(false);
      setError(typeof msg === 'string' ? msg : 'Failed to create product');
      return;
    }
    setIsLoading(false);
  };

  if (!isAddProductModalOpen) return null;

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
        onClick={() => !isLoading && closeAddProductModal()}
      />
      <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-lg relative animate-scale-in overflow-hidden max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 sticky top-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <Plus size={20} />
            </div>
            <h2 className="text-xl font-bold text-slate-800">Add Product</h2>
          </div>
          <button
            onClick={() => !isLoading && closeAddProductModal()}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
            disabled={isLoading}
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-8 space-y-5">
          {error && (
            <div className="p-3 bg-red-50 text-red-600 text-sm rounded-xl border border-red-100">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              required
              disabled={isLoading}
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Price (₹)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              required
              disabled={isLoading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Keywords</label>
            <input
              type="text"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="e.g. wooden, toy, train"
              className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              disabled={isLoading}
            />
            <p className="text-[10px] text-slate-400 mt-1">Comma-separated. Used for search matching.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">Photos</label>
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              multiple
              className="hidden"
              onChange={handlePhotosChange}
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-200 rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer hover:border-primary/50 transition-colors"
            >
              <UploadCloud size={28} className="text-slate-400 mb-2" />
              <p className="text-xs font-medium text-slate-500">Click to upload photos (JPEG, PNG, WebP)</p>
            </div>
            {photos.length > 0 && (
              <div className="grid grid-cols-4 gap-2 mt-3">
                {photos.map((photo, i) => (
                  <div key={i} className="relative aspect-square rounded-lg overflow-hidden border border-slate-100 group">
                    <img src={photo.previewUrl} alt="" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removePhoto(i)}
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
              onClick={closeAddProductModal}
              disabled={isLoading}
              className="flex-1 px-6 py-4 rounded-2xl bg-slate-50 text-slate-600 font-bold hover:bg-slate-100 transition-all active:scale-95 text-[10px] uppercase tracking-widest disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex-[1.5] px-6 py-4 rounded-2xl text-white font-bold transition-all shadow-lg active:scale-95 text-[10px] uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-50 bg-primary hover:bg-primary-dark shadow-primary/20"
            >
              {isLoading ? (
                <><Loader2 size={16} className="animate-spin" /> Creating...</>
              ) : 'Create Product'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
