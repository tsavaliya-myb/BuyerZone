import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';
import { useUIStore } from '@/store/uiStore';

export default function Toast() {
  const { toast, hideToast } = useUIStore();

  if (!toast.isVisible) return null;

  const typeStyles = {
    success: 'bg-green-50 border-green-200 text-green-800',
    error: 'bg-red-50 border-red-200 text-red-800',
    info: 'bg-blue-50 border-blue-200 text-blue-800',
  };

  const Icon = {
    success: CheckCircle,
    error: AlertCircle,
    info: Info,
  }[toast.type];

  const iconColor = {
    success: 'text-green-500',
    error: 'text-red-500',
    info: 'text-blue-500',
  }[toast.type];

  return (
    <div className="fixed top-6 right-6 z-[200] animate-toast-in">
      <div className={`flex items-center gap-3 px-4 py-3 rounded-2xl border shadow-lg max-w-md ${typeStyles[toast.type]}`}>
        <div className={`shrink-0 ${iconColor}`}>
          <Icon size={20} />
        </div>
        <p className="text-sm font-bold leading-tight flex-1">{toast.message}</p>
        <button 
          onClick={hideToast}
          className="p-1 hover:bg-black/5 rounded-lg transition-colors shrink-0"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
