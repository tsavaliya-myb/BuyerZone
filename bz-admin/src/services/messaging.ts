import { api } from "./api";

export interface TelegramSendCodeRequest {
  phone: string;
}

export interface TelegramSendCodeResponse {
  login_id: string;
  expires_in: number;
}

export interface TelegramVerifyCodeRequest {
  login_id: string;
  code: string;
}

export interface TelegramVerifyCodeResponse {
  status: string;
  session_id: string;
  phone: string;
  display_name: string;
}

export interface WhatsappPairRequest {
  phone: string;
}

export interface WhatsappPairResponse {
  code: string;
  expires_in: number;
}

export interface TelegramStatusResponse {
  connected: boolean;
  phone?: string;
  display_name?: string;
  session_id?: string;
}

export interface WhatsappStatusResponse {
  state: string;
  phone?: string;
  display_name?: string;
  session_id?: string;
}

export const messagingService = {
  telegramSendCode: async (data: TelegramSendCodeRequest) => {
    const response = await api.post<TelegramSendCodeResponse>('/admin/telegram/auth/send-code', data);
    return response.data;
  },
  telegramVerifyCode: async (data: TelegramVerifyCodeRequest) => {
    const response = await api.post<TelegramVerifyCodeResponse>('/admin/telegram/auth/verify-code', data);
    return response.data;
  },
  whatsappPair: async (data: WhatsappPairRequest) => {
    const response = await api.post<WhatsappPairResponse>('/admin/whatsapp/pair', data);
    return response.data;
  },
  getTelegramStatus: async () => {
    const response = await api.get<TelegramStatusResponse>('/admin/telegram/auth/status');
    return response.data;
  },
  getWhatsappStatus: async () => {
    const response = await api.get<WhatsappStatusResponse>('/admin/whatsapp/status');
    return response.data;
  }
};
