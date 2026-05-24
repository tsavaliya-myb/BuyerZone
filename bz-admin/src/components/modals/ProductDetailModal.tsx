import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';

export default function ProductDetailModal() {
  const { isProductModalOpen, closeProductModal, selectedProduct } = useUIStore();
  const [isTitleExpanded, setIsTitleExpanded] = useState(false);

  useEffect(() => {
    setIsTitleExpanded(false);
  }, [selectedProduct]);

  if (!isProductModalOpen) return null;

  // Use selected product or default mock data
  const product = selectedProduct || {
    name: 'Stellar-Force Velocity X1',
    sku: 'WH-82719',
    retailer: 'Global Luxe Distributions',
    price: '$142.50',
    precision: 98.4,
    image: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&q=80&w=800', // Mock sneaker image
    history: [
      { date: 'Nov 12, 2023', price: '$148.00', status: 'Bulk Tier 1' },
      { date: 'Nov 05, 2023', price: '$142.50', status: 'Current', isCurrent: true },
      { date: 'Oct 28, 2023', price: '$151.20', status: 'Market Peak' },
    ],
    quote: {
      author: 'Marcus Vance',
      role: 'Seller Representative',
      time: '2:14 PM',
      text: '"We have 500 units remaining for the Q4 allocation. Price is firm at $142.50 but we can waive shipping if you close the PO by Friday."'
    },
    platform: 'Telegram',
    raw_caption: 'A professional-grade athletic sneaker featuring a breathable mesh upper and a responsive cushioned sole for maximum performance and style.'
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 md:p-6">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-md transition-opacity"
        onClick={closeProductModal}
      />

      {/* Modal Content */}
      <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-5xl max-h-full overflow-y-auto flex flex-col md:flex-row relative animate-scale-in custom-scrollbar">
        <button
          onClick={closeProductModal}
          className="absolute top-6 right-6 p-2.5 bg-red-500 text-white hover:bg-red-600 rounded-2xl transition-all z-30 shadow-lg shadow-red-200 active:scale-95"
        >
          <X size={20} strokeWidth={3} />
        </button>
        {/* Left Section: Image */}
        <div className="md:w-1/2 px-6 py-6 md:px-8 md:py-8 bg-slate-50 relative flex flex-col justify-center">
          <div className="flex-1 flex items-center justify-center bg-white rounded-2xl shadow-inner border border-slate-200 overflow-hidden min-h-[180px] md:min-h-[280px]">
            <img
              src={product.image}
              alt={product.name}
              className="w-full h-full object-cover transition-transform hover:scale-105 duration-700"
            />
          </div>
        </div>

        {/* Right Section: Details and Actions */}
        <div className="md:w-1/2 px-6 py-6 md:px-10 md:py-8 flex flex-col relative">
          <header className="mb-4 pr-12 md:pr-0">
            <h2 
              className={`text-2xl md:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight ${
                isTitleExpanded ? '' : 'line-clamp-3'
              }`}
              style={isTitleExpanded ? {} : {
                display: '-webkit-box',
                WebkitLineClamp: 3,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden'
              }}
            >
              {product.name}
            </h2>
            {product.name && product.name.length > 80 && (
              <button
                onClick={() => setIsTitleExpanded(!isTitleExpanded)}
                className="mt-1.5 text-xs font-bold text-primary hover:text-primary-dark hover:underline transition-colors focus:outline-none"
              >
                {isTitleExpanded ? 'Show Less' : 'Show More'}
              </button>
            )}
            <p className="text-slate-500 font-medium mt-1">
              Retailer: <span className="text-slate-900 font-bold">{product.retailer}</span>
              {product.platform && (
                <span className="ml-3 px-2.5 py-1 bg-indigo-50 text-indigo-600 text-[10px] font-bold rounded-lg uppercase border border-indigo-100 tracking-wider">
                  {product.platform}
                </span>
              )}
            </p>
          </header>

          {/* Compact Price Display */}
          <div className="flex items-center justify-between bg-slate-50 border border-slate-100 rounded-xl p-3 mb-4 shadow-sm">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Wholesale Price</span>
            <div className="text-xl font-black text-primary tracking-tight">
              {typeof product.price === 'number'
                ? (product.currency === 'INR' ? `${product.price.toLocaleString()} ₹` : `${product.currency || 'INR'} ${product.price.toLocaleString()}`)
                : (typeof product.price === 'string' && /^\d+(\.\d+)?$/.test(product.price.trim())
                  ? (product.currency === 'INR' ? `${parseFloat(product.price).toLocaleString()} ₹` : `${product.currency || 'INR'} ${parseFloat(product.price).toLocaleString()}`)
                  : product.price)
              }
            </div>
          </div>

          {product.raw_caption && (
            <div className="mb-6 flex-1 flex flex-col min-h-0">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse" />
                <span className="text-[10px] font-black text-primary uppercase tracking-widest">Caption</span>
              </div>
              <div className="bg-primary/5 rounded-2xl border border-primary/10 p-4 overflow-y-auto custom-scrollbar flex-1 max-h-[400px]">
                <p className="text-sm text-slate-700 leading-relaxed font-medium">
                  {product.raw_caption}
                </p>
              </div>
            </div>
          )}


        </div>
      </div>
    </div>
  );
}
