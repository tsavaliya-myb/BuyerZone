import { api } from "./api";

export interface ImageSearchResult {
  product_id: string;
  similarity_score: number;
  name: string;
  price: number;
  currency: string;
  image_url: string;
  wholesaler_name: string | null;
  wholesaler_phone: string | null;
  chat_name: string | null;
  received_at: string;
  status: string;
  platform: string | null;
  raw_caption: string | null;
}

export interface ImageSearchResponse {
  results: ImageSearchResult[];
  total: number;
  query_time_ms: number;
  page?: number;
  size?: number;
}

export const imageSearchService = {
  searchByImage: async (file: File, page: number = 1, size: number = 10, sortBy?: string, sortOrder?: string): Promise<ImageSearchResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('image_base64', '');

    let url = `search/image?page=${page}&size=${size}`;
    if (sortBy) url += `&sortBy=${sortBy}`;
    if (sortOrder) url += `&sortOrder=${sortOrder}`;

    // Do NOT set Content-Type — axios sets it automatically with boundary for FormData
    const response = await api.post<ImageSearchResponse>(url, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    );
    return response.data;
  },

  searchByText: async (query: string, page: number = 1, size: number = 10, sortBy?: string, sortOrder?: string): Promise<ImageSearchResponse> => {
    let url = `search/text?q=${encodeURIComponent(query)}&page=${page}&size=${size}`;
    if (sortBy) url += `&sortBy=${sortBy}`;
    if (sortOrder) url += `&sortOrder=${sortOrder}`;
    const response = await api.get<ImageSearchResponse>(url);
    return response.data;
  },

  searchFromInhouseProduct: async (inhouseProductId: string, page: number = 1, size: number = 10, sortBy?: string, sortOrder?: string): Promise<ImageSearchResponse> => {
    let url = `search/from-inhouse-product?inhouse_product_id=${inhouseProductId}&page=${page}&size=${size}`;
    if (sortBy) url += `&sortBy=${sortBy}`;
    if (sortOrder) url += `&sortOrder=${sortOrder}`;
    const response = await api.get<ImageSearchResponse>(url);
    return response.data;
  },
};
