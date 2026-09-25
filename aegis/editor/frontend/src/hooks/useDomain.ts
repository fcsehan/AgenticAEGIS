import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useDomains() {
  return useQuery({
    queryKey: ["domains"],
    queryFn: api.listDomains,
  });
}

export function useDomain(id: string | undefined) {
  return useQuery({
    queryKey: ["domain", id],
    queryFn: () => api.getDomain(id!),
    enabled: !!id,
  });
}
