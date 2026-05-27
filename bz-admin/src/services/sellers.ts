import { api } from "./api";

export interface Seller {
  id: string;
  chat_id: string;
  chat_name: string;
  chat_type: string;
  phone?: string;
  is_active: boolean;
  added_at: string;
  product_count: number;
}

export interface ChatSearchResult {
  chat_id: string;
  chat_name: string;
  chat_type: string;
  member_count: number;
}

export interface WhatsappChatSearchResult {
  jid: string;
  name: string;
  type: string;
  participant_count: number;
  is_community_parent: boolean;
  is_community_subgroup: boolean;
  already_monitored: boolean;
}

export const sellersService = {
  getSellers: async () => {
    const response = await api.get<Seller[]>('admin/chats');
    return response.data;
  },

  searchChats: async (name: string): Promise<ChatSearchResult[]> => {
    const response = await api.post<ChatSearchResult[]>('admin/chats/search', { name });
    return response.data;
  },

  searchWhatsappChats: async (query: string): Promise<WhatsappChatSearchResult[]> => {
    const response = await api.post<WhatsappChatSearchResult[]>('admin/whatsapp/chats/resolve', { query });
    return response.data;
  },

  addWhatsappSeller: async (data: { jid: string; chat_name: string }): Promise<any> => {
    const response = await api.post<any>('admin/whatsapp/chats/add', data);
    return response.data;
  },

  addWhatsappSellersBatch: async (chats: { jid: string; chat_name: string }[]): Promise<any> => {
    const response = await api.post<any>('admin/whatsapp/chats/add-batch', { chats });
    return response.data;
  },

  addSeller: async (chat_name: string): Promise<Seller> => {
    const response = await api.post<Seller>('admin/chats/add', { chat_name });
    return response.data;
  },

  addSellersBatch: async (chats: { chat_name: string }[]): Promise<Seller[]> => {
    const response = await api.post<Seller[]>('admin/chats/add-batch', { chats });
    return response.data;
  },

  deactivateSeller: async (id: string): Promise<void> => {
    await api.delete(`admin/chats/${id}`);
  },

  updateSellerPhone: async (id: string, phone: string): Promise<Seller> => {
    const response = await api.patch<Seller>(`admin/chats/${id}`, { phone });
    return response.data;
  },
};
