import React, { useState } from 'react';
import { X, Send, Phone, CheckCircle2 } from 'lucide-react';
import { messagingService } from '@/services/messaging';

interface TelegramConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function TelegramConnectModal({ isOpen, onClose }: TelegramConnectModalProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [loginId, setLoginId] = useState('');
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

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const formattedPhone = formatPhoneNumber(phone);
      const response = await messagingService.telegramSendCode({ phone: formattedPhone });
      setLoginId(response.login_id);
      setStep(2);
    } catch (err: any) {
      setError(err.response?.data?.message || err.message || 'Failed to send code');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await messagingService.telegramVerifyCode({ login_id: loginId, code });
      setStep(3);
    } catch (err: any) {
      setError(err.response?.data?.message || err.message || 'Failed to verify code');
    } finally {
      setIsLoading(false);
    }
  };

  const resetAndClose = () => {
    setStep(1);
    setPhone('');
    setCode('');
    setLoginId('');
    setError('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
      <div className="bg-white rounded-3xl shadow-xl w-full max-w-md overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[#0088cc]/10 flex items-center justify-center text-[#0088cc]">
              <Send size={20} />
            </div>
            <h2 className="text-xl font-bold text-slate-800">Connect Telegram</h2>
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
            <form onSubmit={handleSendCode} className="space-y-4">
              <p className="text-slate-500 text-sm mb-4">Enter your phone number connected to your Telegram account to receive a verification code.</p>
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
                    className="block w-full pl-10 pr-3 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#0088cc]/50 focus:border-[#0088cc]/50"
                    required
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 bg-[#0088cc] hover:bg-[#0077b3] text-white rounded-xl font-medium transition-colors disabled:opacity-70 flex items-center justify-center gap-2"
              >
                {isLoading ? 'Sending...' : 'Send Verification Code'}
              </button>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={handleVerifyCode} className="space-y-4">
              <p className="text-slate-500 text-sm mb-4">We've sent a verification code to your Telegram app. Please enter it below.</p>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Verification Code</label>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Enter code"
                  className="block w-full px-4 py-3 border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#0088cc]/50 focus:border-[#0088cc]/50 text-center tracking-widest text-lg font-bold"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 bg-[#0088cc] hover:bg-[#0077b3] text-white rounded-xl font-medium transition-colors disabled:opacity-70 flex items-center justify-center gap-2"
              >
                {isLoading ? 'Verifying...' : 'Verify Code'}
              </button>
              <button
                type="button"
                onClick={() => setStep(1)}
                className="w-full py-2 text-slate-500 hover:text-slate-700 text-sm font-medium transition-colors"
              >
                Back
              </button>
            </form>
          )}

          {step === 3 && (
            <div className="text-center py-6">
              <div className="w-16 h-16 bg-green-100 text-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 size={32} />
              </div>
              <h3 className="text-xl font-bold text-slate-800 mb-2">Successfully Connected!</h3>
              <p className="text-slate-500 mb-6">Your Telegram account has been linked successfully.</p>
              <button
                onClick={resetAndClose}
                className="w-full py-3 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-medium transition-colors"
              >
                Done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
