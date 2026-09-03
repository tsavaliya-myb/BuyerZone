import { api } from "./api";
import type { Seller } from "./sellers";

export interface SellerSearchResponse {
  results: Seller[];
  total: number;
  page?: number;
  size?: number;
}

export const sellerSearchService = {
  searchByText: async (query: string, page: number = 1, size: number = 10): Promise<SellerSearchResponse> => {
    const response = await api.get<SellerSearchResponse>(
      `admin/chats/search-sellers?q=${encodeURIComponent(query)}&page=${page}&size=${size}`
    );
    return response.data;
  },
};
