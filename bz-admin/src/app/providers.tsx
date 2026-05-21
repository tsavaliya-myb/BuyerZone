import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Toast from "@/components/ui/Toast";

const queryClient = new QueryClient();

export const AppProvider = ({ children }: any) => {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toast />
    </QueryClientProvider>
  );
};
