import type { Product } from '@/types/product';

export function useSignedProductUrl(product: Product | undefined): string | undefined {
  // Signed URLs from mission-svc's product catalog are short-lived (typically
  // 15 min). For a viewer session longer than that, add a refetch-on-403 here;
  // out of scope for day-25, called out again in Pitfalls below.
  return product?.url;
}
