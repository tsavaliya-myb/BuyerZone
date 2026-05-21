import { api } from "./api";

export interface DashboardStats {
  total_products: number;
  active_products: number;
  stale_products: number;
  total_wholesalers: number;
  active_chats: number;
  ingested_today: number;
  ingested_this_week: number;
  by_chat: any[];
  by_wholesaler: any[];
}

export interface Product {
  id: string;
  wholesaler_id: string | null;
  wholesaler_name: string | null;
  wholesaler_phone: string | null;
  chat_id: string;
  chat_name: string | null;
  message_id: string;
  name: string;
  raw_caption: string;
  price: number;
  currency: string;
  image_url: string;
  source_platform: string;
  platform: string;
  status: string;
  received_at: string;
  created_at: string;
}

export interface RecentProductsResponse {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const dashboardService = {
  getStats: async () => {
    const response = await api.get<DashboardStats>('admin/stats');
    return response.data;
  },
  getRecentProducts: async (page: number = 1, pageSize: number = 20) => {
    const response = await api.get<RecentProductsResponse>(`internal/products/recent?page=${page}&page_size=${pageSize}`);
    return response.data;
  }
};
