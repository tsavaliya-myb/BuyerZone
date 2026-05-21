import { createBrowserRouter, Navigate } from "react-router-dom";
import Dashboard from "@/features/dashboard";
import ImageSearch from "@/features/image-search";
import Analysis from "@/features/analysis";
import Sellers from "@/features/sellers";
import Export from "@/features/export";
import Notifications from "@/features/notifications";
import Login from "@/features/auth";
import PrivateRoute, { PublicOnlyRoute } from "@/components/auth/PrivateRoute";

export const router = createBrowserRouter([
  {
    // Public only: already logged-in users are redirected to dashboard
    element: <PublicOnlyRoute />,
    children: [
      {
        path: "/login",
        element: <Login />,
      },
    ],
  },
  {
    // All protected routes live under this parent
    element: <PrivateRoute />,
    children: [
      {
        path: "/",
        element: <Dashboard />,
      },
      {
        path: "/image-search",
        element: <ImageSearch />,
      },
      {
        path: "/analysis",
        element: <Analysis />,
      },
      {
        path: "/sellers",
        element: <Sellers />,
      },
      {
        path: "/export",
        element: <Export />,
      },
      {
        path: "/notifications",
        element: <Notifications />,
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
]);
