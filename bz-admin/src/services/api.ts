import axios from "axios";
import { useUIStore } from "@/store/uiStore";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json",
  },
});

// Add token automatically
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle token expiration or unauthorized access
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const showToast = useUIStore.getState().showToast;
    
    if (error.response) {
      const { status, data } = error.response;
      const errorMessage = data?.detail || data?.message || data?.error || (typeof data === 'string' ? data : null) || error.message || "An unexpected error occurred";

      if (status === 401 || status === 403) {
        console.error("Token expired or unauthorized. Redirecting to login...");
        localStorage.removeItem("token");
        // Only redirect if not already on login page to avoid infinite loops
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      } else {
        // Show the actual error message from server for both 4xx and 5xx errors
        showToast(errorMessage, 'error');
      }
    } else if (error.request) {
      // The request was made but no response was received
      showToast("Network error. Please check your connection.", 'error');
    } else {
      // Something happened in setting up the request that triggered an Error
      showToast(error.message, 'error');
    }

    return Promise.reject(error);
  }
);
