import { useEffect, useState } from 'react';
import { ArrowRight, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';
import { dashboardService, type Product } from '@/services/dashboard';

interface RecentlyAnalyzedProps {
  totalProducts?: number;
}

export default function RecentlyAnalyzed({ totalProducts: initialTotal = 0 }: RecentlyAnalyzedProps) {
  const { openProductModal } = useUIStore();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(initialTotal);
  const [totalPages, setTotalPages] = useState(0);
  const pageSize = 30;

  useEffect(() => {
    const fetchRecentProducts = async () => {
      try {
        setLoading(true);
        const data = await dashboardService.getRecentProducts(page, pageSize);
        setProducts(data.items);
        setTotal(data.total);
        setTotalPages(data.pages);
      } catch (error) {
        console.error("Failed to fetch recent products", error);
      } finally {
        setLoading(false);
      }
    };
    fetchRecentProducts();
  }, [page]);

  const handleProductClick = (product: Product) => {
    const sellerName = product.wholesaler_name || product.chat_name || 'Unknown Seller';

    // Map the dashboard product data to the modal format
    const modalData = {
      ...product,
      image: product.image_url,
      seller: sellerName,
      retailer: sellerName,
      precision: 98.4,
      history: [
        { date: new Date(product.created_at).toLocaleDateString(), price: product.currency === 'INR' ? `${product.price?.toLocaleString() ?? '-'} ₹` : `${product.currency} ${product.price?.toLocaleString() ?? '-'}`, status: 'Current', isCurrent: true }
      ],
      quote: {
        author: sellerName,
        role: 'Seller',
        time: new Date(product.received_at).toLocaleTimeString(),
        text: product.name
      }
    };
    openProductModal(modalData);
  };

  const getSellerInitials = (name: string | null) => {
    if (!name) return 'NA';
    return name.substring(0, 2).toUpperCase();
  };

  return (
    <div className="card w-full overflow-hidden">
      <div className="p-6 border-b border-slate-50 flex items-center justify-between">
        <h3 className="font-bold text-slate-800 tracking-tight">Recently Analyzed Products</h3>
        <button className="text-primary text-[11px] font-bold uppercase tracking-wider flex items-center gap-2 hover:underline">
          View All <ArrowRight size={14} />
        </button>
      </div>

      <div className="overflow-x-auto relative min-h-[300px]">
        {loading && (
          <div className="absolute inset-0 bg-white/60 backdrop-blur-[2px] z-10 flex items-center justify-center">
            <div className="flex flex-col items-center gap-2 bg-white p-4 rounded-2xl shadow-xl border border-slate-100">
              <Loader2 className="animate-spin text-primary" size={28} />
              <span className="font-bold text-sm text-slate-600">Loading...</span>
            </div>
          </div>
        )}
        <table className="w-full text-left min-w-[800px]">
          <thead>
            <tr className="bg-[#fcfdff] border-b border-slate-50">
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Product Image</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Product Name</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Seller Name</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Price</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Analysis Date</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {products.length === 0 && !loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-500 font-medium text-sm">
                  No recent products found.
                </td>
              </tr>
            ) : (
              products.map((product) => {
                const sellerName = product.wholesaler_name || product.chat_name || 'Unknown Seller';
                const statusColor = product.status === 'active'
                  ? 'text-blue-600 bg-blue-50 border-blue-100'
                  : 'text-slate-600 bg-slate-50 border-slate-100';
                const dateLabel = new Date(product.received_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

                return (
                  <tr
                    key={product.id}
                    onClick={() => handleProductClick(product)}
                    className="hover:bg-slate-50/50 transition-colors group cursor-pointer"
                  >
                    <td className="px-6 py-6">
                      <div className="w-12 h-12 rounded-lg bg-slate-100 overflow-hidden border border-slate-200 shadow-sm flex items-center justify-center">
                        {product.image_url ? (
                          <img src={product.image_url} alt={product.name} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300" />
                        ) : (
                          <span className="text-[10px] text-slate-400">No Img</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-6 max-w-[250px]">
                      <h4 className="font-bold text-slate-800 text-sm leading-tight truncate" title={product.name}>{product.name}</h4>
                      <p className="text-[10px] font-medium text-slate-400 mt-1 uppercase tracking-wider truncate">MSG ID: {product.message_id}</p>
                    </td>
                    <td className="px-6 py-6 max-w-[200px]">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 shrink-0 rounded-full bg-slate-100 flex items-center justify-center text-[10px] font-bold text-slate-500 border border-slate-200">
                          {getSellerInitials(sellerName)}
                        </div>
                        <span className="text-sm font-semibold text-slate-600 truncate" title={sellerName}>{sellerName}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className="text-sm font-bold text-slate-800">
                        {product.currency === 'INR' ? `${product.price?.toLocaleString() ?? '0'} ₹` : `${product.currency} ${product.price?.toLocaleString() ?? '0'}`}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-center whitespace-nowrap">
                      <span className="text-sm font-medium text-slate-500">{dateLabel}</span>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className={`inline-flex items-center px-3 py-1 rounded-full text-[10px] font-bold border capitalize ${statusColor}`}>
                        {product.status || 'Unknown'}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="p-6 border-t border-slate-50 flex items-center justify-between">
        <p className="text-[11px] font-bold text-slate-400">
          {total > 0
            ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total} products`
            : `Page ${page} · ${products.length} records`
          }
        </p>
        <div className="flex items-center gap-2">
          <button
            disabled={page === 1 || loading}
            onClick={() => setPage(page - 1)}
            className="w-8 h-8 flex items-center justify-center rounded-xl border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="px-3 h-8 flex items-center justify-center rounded-xl bg-primary text-white text-xs font-bold">
            {page}{totalPages ? ` / ${totalPages}` : ''}
          </span>
          <button
            disabled={page >= totalPages || loading}
            onClick={() => setPage(page + 1)}
            className="w-8 h-8 flex items-center justify-center rounded-xl border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
