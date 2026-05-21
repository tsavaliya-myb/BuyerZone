import { api } from "./api";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username?: string;
  name?: string;
  user?: {
    name?: string;
    username?: string;
  };
}

export const authService = {
  login: async (credentials: Record<string, string>) => {
    const response = await api.post<LoginResponse>('admin/login', credentials);
    return response.data;
  },
  logout: () => {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    localStorage.removeItem("user_name");
    window.location.href = "/login";
  }
};
