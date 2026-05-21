import { Navigate, Outlet } from "react-router-dom";

const PrivateRoute = () => {
  const token = localStorage.getItem("token");
  return token ? <Outlet /> : <Navigate to="/login" replace />;
};

export const PublicOnlyRoute = () => {
  const token = localStorage.getItem("token");
  return token ? <Navigate to="/" replace /> : <Outlet />;
};

export default PrivateRoute;
