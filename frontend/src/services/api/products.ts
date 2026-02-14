import { apiFetch, CREATOR_ID } from "./client";
import type { Product } from "./client";

export async function getProducts(creatorId: string = CREATOR_ID): Promise<{ status: string; products: Product[]; count: number }> {
  return apiFetch(`/creator/${creatorId}/products?active_only=false`);
}

export async function addProduct(creatorId: string = CREATOR_ID, product: Omit<Product, "id">): Promise<{ status: string; product: Product }> {
  return apiFetch(`/creator/${creatorId}/products`, { method: "POST", body: JSON.stringify(product) });
}

export async function updateProduct(creatorId: string = CREATOR_ID, productId: string, product: Partial<Product>): Promise<{ status: string; product: Product }> {
  return apiFetch(`/creator/${creatorId}/products/${productId}`, { method: "PUT", body: JSON.stringify(product) });
}

export async function deleteProduct(creatorId: string = CREATOR_ID, productId: string): Promise<{ status: string }> {
  return apiFetch(`/creator/${creatorId}/products/${productId}`, { method: "DELETE" });
}
