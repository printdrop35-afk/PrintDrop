import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { MeOut } from "@/lib/types";

export const ME_KEY = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: () => apiGet<MeOut>("/auth/me"), retry: false, staleTime: 30_000 });
}
