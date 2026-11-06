import { useOutletContext } from "react-router-dom";
import type { MeOut, ShopOut } from "@/lib/types";

export interface DashboardCtx { me: MeOut; shop: ShopOut; can: (perm: string) => boolean }

export function useDashboard(): DashboardCtx {
  return useOutletContext<DashboardCtx>();
}
