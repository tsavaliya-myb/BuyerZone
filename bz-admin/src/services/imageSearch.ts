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
}

export const imageSearchService = {
  searchByImage: async (file: File, topK: number = 10): Promise<ImageSearchResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('image_base64', '');

    // Do NOT set Content-Type — axios sets it automatically with boundary for FormData
    const response = await api.post<ImageSearchResponse>(
      `search/image?top_k=${topK}`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    );
    return response.data;
  },

  searchByText: async (query: string, topK: number = 10): Promise<ImageSearchResponse> => {
    const response = await api.get<ImageSearchResponse>(
      `search/text?q=${encodeURIComponent(query)}&top_k=${topK}`
    );
    return response.data;
  },
};
