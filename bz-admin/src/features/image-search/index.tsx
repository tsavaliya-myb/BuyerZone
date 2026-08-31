import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import {
  UploadCloud, Filter, Download, ChevronLeft, ChevronRight,
  Loader2, AlertCircle, ImageOff, Zap, Clock, Search, Type, Plus
} from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import { useUIStore } from '@/store/uiStore';
import { imageSearchService, type ImageSearchResult } from '@/services/imageSearch';
import { inhouseProductsService, type InHouseProductSuggestion } from '@/services/inhouseProducts';

type SearchMode = 'visual' | 'text';

export default function ImageSearch() {
  const { openProductModal, openAddProductModal } = useUIStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const suggestDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [searchMode, setSearchMode] = useState<SearchMode>('visual');
  const [textQuery, setTextQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [visualSearch, setVisualSearch] = useState({
    results: [] as ImageSearchResult[],
    total: 0,
    page: 1,
    queryTime: null as number | null,
    hasSearched: false,
    error: null as string | null
  });

  const [textSearch, setTextSearch] = useState({
    results: [] as ImageSearchResult[],
    total: 0,
    page: 1,
    queryTime: null as number | null,
    hasSearched: false,
    error: null as string | null,
    searchParams: null as { type: 'text', query: string } | { type: 'inhouse', id: string } | null
  });

  const [suggestions, setSuggestions] = useState<InHouseProductSuggestion[]>([]);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Typeahead against in-house products — fires once the query is 3+ characters
  useEffect(() => {
    if (searchMode !== 'text') return;
    if (suggestDebounceRef.current) clearTimeout(suggestDebounceRef.current);

    const trimmed = textQuery.trim();
    if (trimmed.length < 3) {
      setSuggestions([]);
      setIsSuggesting(false);
      setShowSuggestions(false);
      return;
    }

    setIsSuggesting(true);
    setShowSuggestions(true);
    suggestDebounceRef.current = setTimeout(async () => {
      try {
        const data = await inhouseProductsService.suggest(trimmed, 8);
        setSuggestions(data);
      } catch (err) {
        console.error('Suggest error:', err);
        setSuggestions([]);
      } finally {
        setIsSuggesting(false);
      }
    }, 250);

    return () => {
      if (suggestDebounceRef.current) clearTimeout(suggestDebounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textQuery, searchMode]);

  const handleSelectSuggestion = async (suggestion: InHouseProductSuggestion) => {
    setShowSuggestions(false);
    setIsSearching(true);
    setTextSearch(prev => ({ ...prev, error: null, hasSearched: false }));
    try {
      const response = await imageSearchService.searchFromInhouseProduct(suggestion.id, 1, 10);
      setTextSearch({
        results: response.results,
        total: response.total,
        page: 1,
        queryTime: response.query_time_ms,
        hasSearched: true,
        error: null,
        searchParams: { type: 'inhouse', id: suggestion.id },
      });
    } catch (err: any) {
      console.error('Cross-search error:', err);
      const data = err.response?.data;
      const msg = data?.detail || data?.message || data?.error || (typeof data === 'string' ? data : null);
      setTextSearch(prev => ({
        ...prev,
        error: msg || 'Failed to search matching products.',
        hasSearched: true,
      }));
    } finally {
      setIsSearching(false);
    }
  };

  const handleAddNewProductClick = () => {
    setShowSuggestions(false);
    openAddProductModal(() => {
      const trimmed = textQuery.trim();
      if (trimmed.length >= 3) {
        inhouseProductsService.suggest(trimmed, 8).then(setSuggestions).catch(() => {});
        setShowSuggestions(true);
      }
    });
  };

  const currentSearch = searchMode === 'visual' ? visualSearch : textSearch;
  const { results, total, page, queryTime, hasSearched, error } = currentSearch;

  const handleProductClick = (result: ImageSearchResult) => {
    const modalData = {
      id: result.product_id,
      name: result.name,
      image: result.image_url,
      image_url: result.image_url,
      price: result.price,
      currency: result.currency,
      seller: result.chat_name || result.wholesaler_name || 'Unknown Seller',
      retailer: result.chat_name || result.wholesaler_name || 'Unknown Seller',
      chat_name: result.chat_name,
      wholesaler_name: result.wholesaler_name,
      wholesaler_phone: result.wholesaler_phone,
      status: result.status,
      platform: result.platform,
      raw_caption: result.raw_caption,
      received_at: result.received_at,
      precision: Math.round(result.similarity_score * 100),
      history: [
        {
          date: new Date(result.received_at).toLocaleDateString(),
          price: result.currency === 'INR' ? `${result.price?.toLocaleString() ?? '0'} ₹` : `${result.currency} ${result.price?.toLocaleString() ?? '0'}`,
          status: 'Current',
          isCurrent: true,
        },
      ],
      quote: {
        author: result.chat_name || 'Seller',
        role: 'Wholesale Seller',
        time: new Date(result.received_at).toLocaleTimeString(),
        text: result.name,
      },
    };
    openProductModal(modalData);
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setVisualSearch({
        results: [],
        total: 0,
        page: 1,
        queryTime: null,
        hasSearched: false,
        error: null
      });

      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewImage(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleVisualSearch = async (pageToFetch = 1) => {
    if (!selectedFile) return;

    setIsSearching(true);
    setVisualSearch(prev => ({ ...prev, error: null, hasSearched: false }));

    try {
      const response = await imageSearchService.searchByImage(selectedFile, pageToFetch, 10);
      setVisualSearch({
        results: response.results,
        total: response.total,
        page: pageToFetch,
        queryTime: response.query_time_ms,
        hasSearched: true,
        error: null
      });
    } catch (err: any) {
      console.error('Image search error:', err);
      const data = err.response?.data;
      const msg = data?.detail || data?.message || data?.error || (typeof data === 'string' ? data : null);
      setVisualSearch(prev => ({
        ...prev,
        error: msg || 'Failed to analyze image. Please try again.',
        hasSearched: true
      }));
    } finally {
      setIsSearching(false);
    }
  };

  const handleTextSearch = async (pageToFetch = 1) => {
    if (!textQuery.trim()) return;

    setIsSearching(true);
    setTextSearch(prev => ({ ...prev, error: null, hasSearched: false }));

    try {
      const response = await imageSearchService.searchByText(textQuery.trim(), pageToFetch, 10);
      setTextSearch({
        results: response.results,
        total: response.total,
        page: pageToFetch,
        queryTime: response.query_time_ms,
        hasSearched: true,
        error: null,
        searchParams: { type: 'text', query: textQuery.trim() }
      });
    } catch (err: any) {
      console.error('Text search error:', err);
      const data = err.response?.data;
      const msg = data?.detail || data?.message || data?.error || (typeof data === 'string' ? data : null);
      setTextSearch(prev => ({
        ...prev,
        error: msg || 'Failed to search by text. Please try again.',
        hasSearched: true
      }));
    } finally {
      setIsSearching(false);
    }
  };

  const handleTextSearchPage = async (pageToFetch: number) => {
    const params = textSearch.searchParams;
    if (!params) return;

    setIsSearching(true);
    setTextSearch(prev => ({ ...prev, error: null, hasSearched: false }));

    try {
      let response;
      if (params.type === 'inhouse') {
        response = await imageSearchService.searchFromInhouseProduct(params.id, pageToFetch, 10);
      } else {
        response = await imageSearchService.searchByText(params.query, pageToFetch, 10);
      }
      
      setTextSearch(prev => ({
        ...prev,
        results: response.results,
        total: response.total,
        page: pageToFetch,
        queryTime: response.query_time_ms,
        hasSearched: true,
        error: null
      }));
    } catch (err: any) {
      console.error('Pagination search error:', err);
      const data = err.response?.data;
      const msg = data?.detail || data?.message || data?.error || (typeof data === 'string' ? data : null);
      setTextSearch(prev => ({
        ...prev,
        error: msg || 'Failed to fetch page. Please try again.',
        hasSearched: true
      }));
    } finally {
      setIsSearching(false);
    }
  };

  const getSimilarityColor = (score: number) => {
    if (score >= 0.9) return 'text-emerald-600 bg-emerald-50 border-emerald-100';
    if (score >= 0.7) return 'text-amber-600 bg-amber-50 border-amber-100';
    return 'text-slate-600 bg-slate-50 border-slate-100';
  };

  const handleExport = () => {
    if (!results || results.length === 0) return;

    const headers = ['Product Image', 'Product Name', 'Seller / Channel', 'Price', 'Received At', 'Match Score'];
    const csvContent = [
      headers.join(','),
      ...results.map(result => {
        const dateLabel = new Date(result.received_at).toLocaleDateString(undefined, {
          month: 'short', day: 'numeric', year: 'numeric',
        });
        const scoreLabel = `${Math.round(result.similarity_score * 100)}%`;
        const sellerName = result.chat_name || result.wholesaler_name || 'Unknown Seller';
        const priceLabel = result.currency === 'INR'
          ? `${result.price?.toLocaleString() ?? '0'} ₹`
          : `${result.currency} ${result.price?.toLocaleString() ?? '0'}`;

        return [
          `"${result.image_url || ''}"`,
          `"${result.name?.replace(/"/g, '""') || ''}"`,
          `"${sellerName?.replace(/"/g, '""')}"`,
          `"${priceLabel}"`,
          `"${dateLabel}"`,
          `"${scoreLabel}"`
        ].join(',');
      })
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `search_results_${Date.now()}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <MainLayout>
      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept="image/*"
        onChange={handleFileChange}
      />

      {/* Header & Tabs */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">AI Multi-Search</h1>
          <p className="text-slate-500 font-medium mt-1">
            Identify products using visual recognition or semantic text search.
          </p>
        </div>

        <div className="flex bg-slate-100 p-1 rounded-2xl border border-slate-200 shadow-inner w-fit self-start md:self-auto">
          <button
            onClick={() => setSearchMode('visual')}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-black transition-all ${searchMode === 'visual'
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
              }`}
          >
            <UploadCloud size={16} />
            Visual Search
          </button>
          <button
            onClick={() => setSearchMode('text')}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-black transition-all ${searchMode === 'text'
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'
              }`}
          >
            <Type size={16} />
            Text Search
          </button>
        </div>
      </div>
      {/* Input Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
        {searchMode === 'visual' ? (
          <>
            {/* Upload Zone */}
            <div
              onClick={handleUploadClick}
              className="lg:col-span-2 card bg-white border-2 border-dashed border-slate-200 p-12 flex flex-col items-center justify-center text-center cursor-pointer hover:border-primary/50 transition-colors group"
            >
              <div className="w-20 h-20 bg-primary-light rounded-full flex items-center justify-center text-primary mb-6 group-hover:scale-110 transition-transform">
                <UploadCloud size={36} />
              </div>
              <h3 className="text-xl font-bold text-slate-800 mb-2 tracking-tight">Drop product image here</h3>
              <p className="text-sm text-slate-400 mb-4 max-w-xs mx-auto font-medium">
                Upload a JPEG, PNG or WebP file to find matching wholesale products.
              </p>
              {selectedFile && (
                <p className="text-xs font-bold text-primary mb-4 bg-primary-light px-3 py-1.5 rounded-lg">
                  📎 {selectedFile.name}
                </p>
              )}
              <button className="btn btn-primary px-8 h-12 gap-2 shadow-lg shadow-primary/20 pointer-events-none">
                <UploadCloud size={18} />
                {selectedFile ? 'Change Image' : 'Upload Product Image'}
              </button>
            </div>

            {/* Live Preview Card */}
            <div className="card bg-white p-6">
              <div className="flex items-center justify-between mb-6">
                <div className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-lg shadow-sm border ${isSearching
                  ? 'text-primary bg-primary-light border-primary/10'
                  : hasSearched
                    ? 'text-emerald-600 bg-emerald-50 border-emerald-100'
                    : 'text-slate-400 bg-slate-50 border-slate-100'
                  }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${isSearching ? 'bg-primary animate-pulse' : hasSearched ? 'bg-emerald-500' : 'bg-slate-300'
                    }`} />
                  {isSearching ? 'AI Processing' : hasSearched ? 'Done' : 'Ready'}
                </div>

                {previewImage && !isSearching && (
                  <button
                    onClick={() => handleVisualSearch(1)}
                    className="text-[10px] font-extrabold text-white bg-slate-900 px-3 py-1.5 rounded-lg hover:bg-primary transition-all active:scale-95 shadow-lg shadow-slate-200 uppercase tracking-wider flex items-center gap-1.5"
                  >
                    <Zap size={12} />
                    Start Analysis
                  </button>
                )}
              </div>

              <div className="aspect-square rounded-2xl bg-slate-900 overflow-hidden mb-6 shadow-inner relative group">
                <img
                  src={previewImage || 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop'}
                  alt="Product Preview"
                  className={`w-full h-full object-cover transition-transform duration-500 ${previewImage ? 'opacity-100' : 'opacity-40'}`}
                />
                {isSearching && (
                  <div className="absolute inset-0 bg-slate-900/50 flex flex-col items-center justify-center gap-3">
                    <Loader2 className="animate-spin text-primary" size={36} />
                    <p className="text-white text-xs font-bold uppercase tracking-widest">Searching...</p>
                  </div>
                )}
                {!previewImage && !isSearching && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-32 h-32 border-2 border-primary/50 rounded-3xl animate-pulse" />
                  </div>
                )}
              </div>

              <div className="flex justify-between items-end">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Status</p>
                  <h5 className="font-bold text-slate-800">
                    {isSearching ? 'Analyzing...' : hasSearched ? `${total} match${total !== 1 ? 'es' : ''} found` : previewImage ? 'Ready to scan' : 'No image'}
                  </h5>
                </div>
                {queryTime !== null && (
                  <div className="text-right">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Query Time</p>
                    <h5 className="font-bold text-primary text-sm flex items-center gap-1">
                      <Clock size={12} /> {queryTime.toFixed(1)}ms
                    </h5>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="lg:col-span-3 card bg-white p-8 flex flex-col items-center justify-center text-center">
            <div className="w-14 h-14 bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600 mb-4 shadow-sm">
              <Search size={24} />
            </div>
            <h3 className="text-xl font-black text-slate-800 mb-2 tracking-tight">Semantic Text Search</h3>
            <p className="text-xs text-slate-500 mb-8 max-w-sm mx-auto font-medium leading-relaxed">
              Find wholesale products by name, description or keywords. Our AI understands context to find the best matches.
            </p>

            <div className="w-full max-w-xl relative group">
              <div className="absolute inset-y-0 left-5 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-slate-400 group-focus-within:text-primary transition-colors" />
              </div>
              <input
                type="text"
                placeholder="Search products..."
                value={textQuery}
                onChange={(e) => setTextQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleTextSearch(1)}
                onFocus={() => { if (textQuery.trim().length >= 3) setShowSuggestions(true); }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                className="block w-full pl-14 pr-28 py-4 bg-slate-50 border-2 border-slate-100 rounded-2xl text-base font-bold text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-8 focus:ring-primary/5 focus:border-primary focus:bg-white transition-all shadow-sm"
                autoFocus
              />
              <button
                onClick={() => handleTextSearch(1)}
                disabled={isSearching || !textQuery.trim()}
                className="absolute right-2 top-2 bottom-2 px-6 bg-slate-900 text-white rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-lg shadow-slate-200"
              >
                {isSearching ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
                {isSearching ? 'Searching...' : 'Search'}
              </button>

              {showSuggestions && (
                <div className="absolute left-0 right-0 top-full mt-2 bg-white rounded-2xl shadow-xl border border-slate-100 overflow-hidden z-20 text-left">
                  {isSuggesting ? (
                    <div className="p-4 flex items-center gap-2 text-slate-400 text-sm font-medium">
                      <Loader2 size={16} className="animate-spin" /> Searching in-house products...
                    </div>
                  ) : suggestions.length > 0 ? (
                    <ul className="max-h-72 overflow-y-auto divide-y divide-slate-50">
                      {suggestions.map((s) => (
                        <li
                          key={s.id}
                          onMouseDown={() => handleSelectSuggestion(s)}
                          className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 cursor-pointer transition-colors"
                        >
                          <div className="w-9 h-9 rounded-lg bg-slate-100 overflow-hidden border border-slate-100 flex items-center justify-center flex-shrink-0">
                            {s.thumbnail_url ? (
                              <img src={s.thumbnail_url} alt={s.name} className="w-full h-full object-cover" />
                            ) : (
                              <ImageOff size={14} className="text-slate-300" />
                            )}
                          </div>
                          <span className="text-sm font-bold text-slate-700">{s.name}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="p-4 flex flex-col items-center gap-3">
                      <p className="text-xs text-slate-400 font-medium">No matching in-house products found.</p>
                      <button
                        type="button"
                        onMouseDown={handleAddNewProductClick}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-xs font-bold hover:bg-primary-dark transition-all"
                      >
                        <Plus size={14} /> Add New Product
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="mt-8 flex items-center gap-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              <span>Popular:</span>
              <button onClick={() => { setTextQuery('train'); }} className="hover:text-primary transition-colors">"train"</button>
              <span className="w-1 h-1 bg-slate-200 rounded-full"></span>
              <button onClick={() => { setTextQuery('wooden blocks'); }} className="hover:text-primary transition-colors">"wooden blocks"</button>
              <span className="w-1 h-1 bg-slate-200 rounded-full"></span>
              <button onClick={() => { setTextQuery('drone'); }} className="hover:text-primary transition-colors">"drone"</button>
            </div>
          </div>
        )}
      </div>

      {/* Results Section */}
      <div className="card bg-white overflow-hidden shadow-sm">
        <div className="p-6 border-b border-slate-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="font-bold text-slate-800 tracking-tight">Wholesale Match Results</h3>
            <p className="text-[11px] text-slate-400 font-medium mt-1">
              {hasSearched
                ? error
                  ? 'Search failed. Please try again.'
                  : `Found ${total} matching product${total !== 1 ? 's' : ''} for your ${searchMode === 'visual' ? 'image' : 'query'}.`
                : searchMode === 'visual'
                  ? 'Upload an image to start visual analysis.'
                  : 'Enter keywords above to start semantic search.'
              }
            </p>
          </div>
          {hasSearched && !error && results.length > 0 && (
            <div className="flex items-center gap-3">
              <button className="flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-600 rounded-lg text-xs font-bold hover:bg-slate-200 transition-colors">
                <Filter size={14} /> Filter
              </button>
              <button
                onClick={handleExport}
                className="flex items-center gap-2 px-4 py-2 bg-slate-800 text-white rounded-lg text-xs font-bold hover:bg-slate-900 transition-colors"
              >
                <Download size={14} /> Export
              </button>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[900px]">
            <thead>
              <tr className="bg-[#fcfdff] border-b border-slate-50 uppercase text-[10px] font-bold text-slate-400 tracking-widest">
                <th className="px-6 py-4">Product Image</th>
                <th className="px-6 py-4">Product Name</th>
                <th className="px-6 py-4">Seller / Channel</th>
                <th className="px-6 py-4">Price</th>
                {/* <th className="px-6 py-4">Phone</th> */}
                <th className="px-6 py-4 text-center">Received At</th>
                <th className="px-6 py-4 text-center">Match Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">

              {/* Loading State */}
              {isSearching && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <Loader2 className="animate-spin text-primary" size={32} />
                      <p className="text-slate-400 font-medium text-sm">Searching wholesale database...</p>
                    </div>
                  </td>
                </tr>
              )}

              {/* Error State */}
              {!isSearching && error && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <AlertCircle className="text-red-400" size={32} />
                      <p className="text-red-500 font-bold text-sm">{error}</p>
                    </div>
                  </td>
                </tr>
              )}

              {/* Empty / No Search State */}
              {!isSearching && !error && !hasSearched && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center text-slate-300">
                        {searchMode === 'visual' ? <UploadCloud size={32} /> : <Search size={32} />}
                      </div>
                      <p className="text-slate-400 font-medium text-sm">
                        {searchMode === 'visual'
                          ? 'Upload an image and click Start Analysis'
                          : 'Enter product keywords and click Search'
                        }
                      </p>
                    </div>
                  </td>
                </tr>
              )}

              {/* No Results Found */}
              {!isSearching && !error && hasSearched && results.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <ImageOff className="text-slate-300" size={32} />
                      <p className="text-slate-400 font-medium text-sm">No matching products found for this search.</p>
                    </div>
                  </td>
                </tr>
              )}

              {/* Actual Results */}
              {!isSearching && !error && results.map((result) => {
                const dateLabel = new Date(result.received_at).toLocaleDateString(undefined, {
                  month: 'short', day: 'numeric', year: 'numeric',
                });
                const scoreLabel = `${Math.round(result.similarity_score * 100)}%`;
                const sellerName = result.chat_name || result.wholesaler_name || 'Unknown';

                return (
                  <tr
                    key={result.product_id}
                    onClick={() => handleProductClick(result)}
                    className="hover:bg-slate-50/50 transition-colors group cursor-pointer"
                  >
                    <td className="px-6 py-4">
                      <div className="w-12 h-12 rounded-lg bg-slate-100 overflow-hidden border border-slate-100 flex items-center justify-center">
                        {result.image_url ? (
                          <img
                            src={result.image_url}
                            alt={result.name}
                            className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                            onError={(e) => {
                              (e.target as HTMLImageElement).src = 'https://via.placeholder.com/48?text=NA';
                            }}
                          />
                        ) : (
                          <ImageOff size={20} className="text-slate-300" />
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 max-w-[250px]">
                      <h4 className="font-bold text-slate-800 text-sm leading-snug line-clamp-2" title={result.name}>{result.name}</h4>
                      <p className="text-[10px] font-medium text-slate-400 mt-0.5 uppercase tracking-wider truncate">
                        ID: {result.product_id.slice(0, 8)}...
                      </p>
                    </td>

                    <td className="px-6 py-4 font-medium text-slate-600 text-sm">{sellerName}</td>
                    <td className="px-6 py-4 text-sm font-bold text-primary">
                      {result.currency === 'INR' ? `${result.price?.toLocaleString() ?? '0'} ₹` : `${result.currency} ${result.price?.toLocaleString() ?? '0'}`}
                    </td>
                    {/* <td className="px-6 py-4 text-sm text-slate-500 font-medium">
                      {result.wholesaler_phone || 'N/A'}
                    </td> */}
                    <td className="px-6 py-4 text-center text-sm font-medium text-slate-500">
                      {dateLabel}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${getSimilarityColor(result.similarity_score)}`}>
                        {scoreLabel}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        {hasSearched && !error && results.length > 0 && (
          <div className="p-6 border-t border-slate-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <p className="text-[11px] font-medium text-slate-400">
              Showing {results.length} of {total} matches
              {queryTime !== null && ` · ${queryTime.toFixed(1)}ms`}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => searchMode === 'visual' ? handleVisualSearch(page - 1) : handleTextSearchPage(page - 1)}
                disabled={page <= 1 || isSearching}
                className="w-8 h-8 flex items-center justify-center rounded-lg border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors disabled:opacity-40"
              >
                <ChevronLeft size={16} />
              </button>
              <button className="w-8 h-8 flex items-center justify-center rounded-lg bg-primary text-white text-xs font-bold">
                {page}
              </button>
              <button
                onClick={() => searchMode === 'visual' ? handleVisualSearch(page + 1) : handleTextSearchPage(page + 1)}
                disabled={page * 10 >= total || isSearching}
                className="w-8 h-8 flex items-center justify-center rounded-lg border border-slate-100 text-slate-400 hover:bg-slate-50 transition-colors disabled:opacity-40"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </MainLayout>
  );
}
