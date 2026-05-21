✅ Recommended Stack (Production Level)
Use this stack for long-term:

React (Vite)
TypeScript
Tailwind CSS
Axios
React Query (TanStack Query)
React Router
Zustand (state)


📁 Project Structure (Reusable)


├── features/           # Feature-based modules
│   ├── dashboard/
│   ├── image-search/
│   ├── analysis/
│   ├── sellers/
│
├── services/           # API calls
│   ├── api.ts
│   ├── endpoints.ts
│
├── hooks/              # Custom hooks
│   ├── useAuth.ts
│   ├── useDebounce.ts
│
├── store/              # Global state (Zustand)
│   ├── authStore.ts
│
├── utils/              # Helpers
│   ├── format.ts
│   ├── constants.ts
│
├── types/              # TypeScript types
│   ├── index.ts
│
├── assets/             # Images/icons
│
├── styles/             # Global styles
│
└── main.tsx


🔥 Core Reusable Files (IMPORTANT)
1️⃣ API Base Setup (reuse in all projects)

// services/api.ts
import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add token automatically
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
}); 

React Query Setup

// app/providers.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient();

export const AppProvider = ({ children }: any) => {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

3️⃣ Layout (Reusable for all dashboards)

// components/layout/MainLayout.tsx
import Sidebar from "./Sidebar";
import Navbar from "./Navbar";

export default function MainLayout({ children }: any) {
  return (
    <div className="flex">
      <Sidebar />
      <div className="flex-1">
        <Navbar />
        <main className="p-4">{children}</main>
      </div>
    </div>
  );
}


4️⃣ Routing Structure

// app/router.tsx
import { createBrowserRouter } from "react-router-dom";
import Dashboard from "@/features/dashboard";
import ImageSearch from "@/features/image-search";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Dashboard />,
  },
  {
    path: "/image-search",
    element: <ImageSearch />,
  },
]);

Create a reusable React starter (boilerplate) with:
Dashboard layout
API handling
Auth-ready structure
Reusable components
Scalable folder structure

7️⃣ Environment Config (reusable)
VITE_API_URL=http://localhost:8000
