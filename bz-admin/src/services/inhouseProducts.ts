import { api } from "./api";

export interface InHouseProductPhoto {
  id: string;
  url: string;
  position: number;
}

export interface InHouseProduct {
  id: string;
  name: string;
  price: number;
  keywords: string[];
  status: string;
  photos: InHouseProductPhoto[];
  created_at: string;
  updated_at: string;
}

export interface InHouseProductListResponse {
  items: InHouseProduct[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface InHouseProductUpdate {
  name?: string;
  price?: number;
  keywords?: string[];
  status?: string;
}

export const inhouseProductsService = {
  list: async (params: { keyword?: string; status?: string; page?: number; page_size?: number } = {}): Promise<InHouseProductListResponse> => {
    const response = await api.get<InHouseProductListResponse>("admin/inhouse-products", { params });
    return response.data;
  },

  get: async (id: string): Promise<InHouseProduct> => {
    const response = await api.get<InHouseProduct>(`admin/inhouse-products/${id}`);
    return response.data;
  },

  create: async (data: { name: string; price: number; keywords: string[]; photos: File[] }): Promise<InHouseProduct> => {
    const formData = new FormData();
    formData.append("name", data.name);
    formData.append("price", String(data.price));
    formData.append("keywords", data.keywords.join(","));
    data.photos.forEach((file) => formData.append("photos", file));

    const response = await api.post<InHouseProduct>("admin/inhouse-products", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  },

  update: async (id: string, data: InHouseProductUpdate): Promise<InHouseProduct> => {
    const response = await api.patch<InHouseProduct>(`admin/inhouse-products/${id}`, data);
    return response.data;
  },

  remove: async (id: string): Promise<void> => {
    await api.delete(`admin/inhouse-products/${id}`);
  },

  addPhotos: async (id: string, photos: File[]): Promise<InHouseProduct> => {
    const formData = new FormData();
    photos.forEach((file) => formData.append("photos", file));

    const response = await api.post<InHouseProduct>(`admin/inhouse-products/${id}/photos`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  },

  removePhoto: async (id: string, photoId: string): Promise<InHouseProduct> => {
    const response = await api.delete<InHouseProduct>(`admin/inhouse-products/${id}/photos/${photoId}`);
    return response.data;
  },
};
