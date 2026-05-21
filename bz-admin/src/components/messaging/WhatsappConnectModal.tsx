import React, { useState } from 'react';
import { X, Phone, MessageCircle } from 'lucide-react';
import { messagingService } from '@/services/messaging';

interface WhatsappConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function WhatsappConnectModal({ isOpen, onClose }: WhatsappConnectModalProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [phone, setPhone] = useState('');
  const [pairingCode, setPairingCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const formatPhoneNumber = (input: string) => {
    const cleaned = input.replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `91${cleaned}`;
    }
    return cleaned;
  };

  const handlePair = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const formattedPhone = formatPhoneNumber(phone);
      const response = await messagingService.whatsappPair({ phone: formattedPhone });
      setPairingCode(response.code);
      setStep(2);
    } catch (err: any) {
      setError(err.response?.data?.message || err.message || 'Failed to initiate pairing');
    } finally {
      setIsLoading(false);
    }
  };

  const resetAndClose = () => {
    setStep(1);
    setPhone('');
    setPairingCode('');
    setError('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
      <div className="bg-white rounded-3xl shadow-xl w-full max-w-md overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[#25D366]/10 flex items-center justify-center text-[#25D366]">
              <MessageCircle size={20} />
            </div>
            <h2 className="text-xl font-bold text-slate-800">Connect WhatsApp</h2>
          </div>
          <button
            onClick={resetAndClose}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 text-red-600 text-sm rounded-xl border border-red-100">
              {error}
            </div>
          )}

          {step === 1 && (
            <form onSubmit={handlePair} className="space-y-4">
              <p className="text-slate-500 text-sm mb-4">Enter your phone number to pair your device with WhatsApp.</p>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Phone Number</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Phone size={18} className="text-slate-400" />
                  </div>
                  <input
                    type="text"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+1234567890"
                    className="block w-full pl-10 pr-3 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#25D366]/50 focus:border-[#25D366]/50"
                    required
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 bg-[#25D366] hover:bg-[#128C7E] text-white rounded-xl font-medium transition-colors disabled:opacity-70 flex items-center justify-center gap-2"
              >
                {isLoading ? 'Generating Code...' : 'Get Pairing Code'}
              </button>
            </form>
          )}

          {step === 2 && (
            <div className="text-center py-6">
              <h3 className="text-lg font-bold text-slate-800 mb-2">Pairing Code</h3>
              <p className="text-slate-500 text-sm mb-6">Enter this code on your WhatsApp device to complete the pairing process.</p>
              
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 mb-8">
                <p className="text-4xl font-mono font-bold tracking-widest text-[#25D366]">{pairingCode}</p>
              </div>

              <div className="space-y-3">
                <button
                  onClick={resetAndClose}
                  className="w-full py-3 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium transition-colors"
                >
                  Done
                </button>
                <button
                  onClick={() => setStep(1)}
                  className="w-full py-2 text-slate-500 hover:text-slate-700 text-sm font-medium transition-colors"
                >
                  Start Over
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
