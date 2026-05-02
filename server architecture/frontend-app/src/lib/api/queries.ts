// Server-state hooks. One module to keep cache keys in one place.

import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export const queryKeys = {
  health: ["health"] as const,
  bilanFiles: (limit?: number) => ["bilan", "files", { limit }] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => {
      const { data, error } = await api.GET("/health");
      if (error) throw error;
      return data!;
    },
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function useBilanFiles(limit = 50) {
  return useQuery({
    queryKey: queryKeys.bilanFiles(limit),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/bilan/files", {
        params: { query: { limit } },
      });
      if (error) throw error;
      return data!;
    },
    staleTime: 5 * 60 * 1000,
  });
}
