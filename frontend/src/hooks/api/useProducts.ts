import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getProducts, addProduct, updateProduct, deleteProduct, apiKeys, getCreatorId } from "@/services/api";
import type { Product } from "@/types/api";

export function useProducts(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.products(creatorId),
    queryFn: () => getProducts(creatorId),
    staleTime: 60000,
  });
}

export function useAddProduct(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (product: Omit<Product, "id">) => addProduct(creatorId, product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.products(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

export function useUpdateProduct(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, product }: { productId: string; product: Partial<Product> }) => updateProduct(creatorId, productId, product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.products(creatorId) });
    },
  });
}

export function useDeleteProduct(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) => deleteProduct(creatorId, productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.products(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}
