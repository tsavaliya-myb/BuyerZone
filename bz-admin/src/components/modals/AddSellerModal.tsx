import { X, Search, Users, Plus, Check, Loader2, Send, MessageCircle } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';
import { useState, useEffect, useRef } from 'react';
import { sellersService, type ChatSearchResult, type WhatsappChatSearchResult } from '@/services/sellers';

export default function AddSellerModal() {
  const { isAddSellerModalOpen, closeAddSellerModal, onSellerAdded } = useUIStore();

  const [platform, setPlatform] = useState<'telegram' | 'whatsapp'>('telegram');
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<(ChatSearchResult | WhatsappChatSearchResult)[]>([]);
  const [selectedSeller, setSelectedSeller] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isAddSellerModalOpen) {
      setPlatform('telegram');
      setSearchQuery('');
      setResults([]);
      setSelectedSeller(null);
      setError(null);
      setSuccess(false);
      setIsSearching(false);
    }
  }, [isAddSellerModalOpen]);

  // Handle platform change
  const handlePlatformChange = (newPlatform: 'telegram' | 'whatsapp') => {
    setPlatform(newPlatform);
    setSearchQuery('');
    setResults([]);
    setSelectedSeller(null);
    setError(null);
  };

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (searchQuery.trim().length < 2) {
      setResults([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    debounceRef.current = setTimeout(async () => {
      try {
        if (platform === 'telegram') {
          const data = await sellersService.searchChats(searchQuery.trim());
          setResults(data);
        } else {
          const data = await sellersService.searchWhatsappChats(searchQuery.trim());
          setResults(data);
        }
        setError(null);
      } catch (err) {
        console.error("Search error:", err);
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 400);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQuery]);

  const handleAdd = async () => {
    const nameToAdd = selectedSeller || searchQuery.trim();
    if (!nameToAdd) return;

    setIsAdding(true);
    setError(null);
    try {
      if (platform === 'telegram') {
        console.log("Adding telegram seller:", nameToAdd);
        await sellersService.addSeller(nameToAdd);
      } else {
        console.log("Adding whatsapp seller:", nameToAdd);
        let chat_name = nameToAdd;
        if (selectedSeller) {
          const selectedItem = results.find(r => (r as WhatsappChatSearchResult).jid === selectedSeller);
          if (selectedItem) {
            chat_name = (selectedItem as WhatsappChatSearchResult).name;
          }
        }
        await sellersService.addWhatsappSeller({ jid: nameToAdd, chat_name });
      }
      setSuccess(true);

      // TRIGGER REFRESH
      if (onSellerAdded) {
        console.log("Triggering refresh callback...");
        onSellerAdded();
      }

      // Close after a short delay to show success state
      setTimeout(() => {
        closeAddSellerModal();
      }, 1500);
    } catch (err: any) {
      console.error("Add seller error:", err);
      const data = err.response?.data;
      let serverMessage: string | null = null;
      if (data) {
        if (typeof data === 'string') {
          serverMessage = data;
        } else if (typeof data === 'object') {
          const detail = data.detail;
          if (detail) {
            serverMessage = typeof detail === 'string' ? detail : (detail.error || detail.message || JSON.stringify(detail));
          } else {
            serverMessage = data.message || data.error || JSON.stringify(data);
          }
        }
      }
      setError(serverMessage || "Failed to add seller. Please try again.");
    } finally {
      setIsAdding(false);
    }
  };

  if (!isAddSellerModalOpen) return null;

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 md:p-6">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-md" onClick={closeAddSellerModal} />

      {/* Modal */}
      <div className="bg-white rounded-[32px] shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col relative animate-scale-in">

        {/* Header */}
        <div className="p-8 border-b border-slate-50 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-primary rounded-2xl flex items-center justify-center text-white shadow-lg shadow-primary/20">
              <Users size={24} />
            </div>
            <div>
              <h2 className="text-xl font-black text-slate-800 tracking-tight">Add New Seller</h2>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Search or Enter Channel Name</p>
            </div>
          </div>
          <button onClick={closeAddSellerModal} className="p-2.5 bg-white text-slate-400 hover:text-slate-600 rounded-xl transition-all border border-slate-100 shadow-sm active:scale-95">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="p-8 flex-1 overflow-y-auto custom-scrollbar">

          {/* Platform Toggle */}
          <div className="flex bg-slate-100 p-1 rounded-2xl mb-6">
            <button
              onClick={() => handlePlatformChange('telegram')}
              className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition-all ${platform === 'telegram'
                  ? 'bg-white text-[#229ED9] shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
                }`}
            >
              <Send size={18} />
              Telegram
            </button>
            <button
              onClick={() => handlePlatformChange('whatsapp')}
              className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition-all ${platform === 'whatsapp'
                  ? 'bg-white text-[#25D366] shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
                }`}
            >
              <MessageCircle size={18} />
              WhatsApp
            </button>
          </div>

          {/* Search Box */}
          <div className="relative mb-6">
            {isSearching ? (
              <Loader2 className="absolute left-5 top-1/2 -translate-y-1/2 text-primary animate-spin" size={20} />
            ) : (
              <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
            )}
            <input
              type="text"
              placeholder={platform === 'telegram' ? "Type channel name (e.g. Toyerzone)..." : "Type WhatsApp group/community name..."}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSelectedSeller(null);
                setError(null);
              }}
              className="w-full pl-14 pr-6 py-4 bg-slate-50 border-2 border-slate-100 rounded-2xl text-base font-medium focus:ring-4 focus:ring-primary/5 focus:border-primary transition-all outline-none placeholder:text-slate-400"
              autoFocus
            />
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-100 rounded-2xl text-red-600 text-sm font-bold flex items-center gap-3">
              <div className="w-2 h-2 bg-red-500 rounded-full"></div>
              {error}
            </div>
          )}

          {/* Success Message */}
          {success && (
            <div className="mb-6 p-4 bg-emerald-50 border border-emerald-100 rounded-2xl text-emerald-600 text-sm font-bold flex items-center gap-3 animate-bounce">
              <Check size={20} />
              Seller added successfully! Refreshing list...
            </div>
          )}

          {/* Results Area */}
          <div className="space-y-3">
            {searchQuery.trim().length < 2 ? (
              <div className="py-12 text-center">
                <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center text-slate-300 mx-auto mb-4">
                  <Search size={32} />
                </div>
                <p className="text-slate-400 font-medium text-sm">Type at least 2 characters to search</p>
              </div>
            ) : isSearching ? (
              <div className="py-12 text-center">
                <Loader2 className="animate-spin text-primary mx-auto mb-3" size={32} />
                <p className="text-slate-400 font-medium text-sm">Searching {platform === 'telegram' ? 'Telegram' : 'WhatsApp'}...</p>
              </div>
            ) : results.length === 0 ? (
              <div className="py-8 px-6 bg-slate-50 rounded-[24px] border-2 border-dashed border-slate-200 text-center">
                <p className="text-slate-500 font-bold mb-2">No results found for "{searchQuery}"</p>
                <p className="text-[10px] text-slate-400 uppercase tracking-widest">You can still try to add it manually by clicking the button below.</p>
              </div>
            ) : (
              <>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-1 mb-2">Search Results</p>
                {results.map((item, idx) => {
                  const isTelegram = platform === 'telegram';
                  const tgItem = item as ChatSearchResult;
                  const waItem = item as WhatsappChatSearchResult;

                  const id = isTelegram ? tgItem.chat_id : waItem.jid;
                  const name = isTelegram ? tgItem.chat_name : waItem.name;
                  const type = isTelegram ? tgItem.chat_type : waItem.type;
                  const members = isTelegram ? tgItem.member_count : waItem.participant_count;
                  // Use ID as the value to send if WhatsApp, else use name for Telegram
                  // Wait, actually for Telegram the current implementation uses chat_name. Let's keep it.
                  // For WhatsApp we'll use jid.
                  const selectionValue = isTelegram ? name : id;

                  return (
                    <div
                      key={id || idx}
                      onClick={() => setSelectedSeller(selectionValue)}
                      className={`p-5 rounded-[20px] border-2 transition-all cursor-pointer flex items-center justify-between ${selectedSeller === selectionValue
                          ? 'border-primary bg-primary/5 shadow-md shadow-primary/5'
                          : 'border-slate-100 bg-white hover:border-slate-200'
                        }`}
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm shrink-0 ${selectedSeller === selectionValue
                            ? (isTelegram ? 'bg-[#229ED9] text-white' : 'bg-[#25D366] text-white')
                            : 'bg-slate-100 text-slate-500'
                          }`}>
                          {name?.substring(0, 1).toUpperCase() || '?'}
                        </div>
                        <div>
                          <h4 className="font-bold text-slate-800 text-sm">{name}</h4>
                          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mt-0.5">
                            {type} · {members?.toLocaleString()} members
                            {!isTelegram && waItem.is_community_parent && ' · Community'}
                            {!isTelegram && waItem.is_community_subgroup && ' · Subgroup'}
                          </p>
                        </div>
                      </div>
                      <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all shrink-0 ${selectedSeller === selectionValue
                          ? 'bg-primary border-primary text-white'
                          : 'border-slate-200 text-transparent'
                        }`}>
                        <Check size={14} strokeWidth={3} />
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-8 bg-slate-50/50 border-t border-slate-50 flex gap-4">
          <button
            onClick={closeAddSellerModal}
            className="flex-1 px-6 py-4 rounded-2xl bg-white text-slate-600 font-bold border border-slate-200 hover:bg-slate-50 transition-all active:scale-95 text-sm uppercase tracking-widest"
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={(!selectedSeller && !searchQuery.trim()) || isAdding || success}
            className="flex-[2] px-10 py-4 rounded-2xl bg-primary text-white font-bold hover:bg-primary-dark transition-all shadow-lg shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 text-sm uppercase tracking-widest flex items-center justify-center gap-2"
          >
            {isAdding ? (
              <><Loader2 size={18} className="animate-spin" /> Adding...</>
            ) : success ? (
              <><Check size={18} /> Done!</>
            ) : (
              <><Plus size={18} /> Confirm Addition</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
