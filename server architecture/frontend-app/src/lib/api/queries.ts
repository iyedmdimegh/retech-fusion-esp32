// Server-state hooks. One module to keep cache keys in one place.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./types";

export type BilanFile = components["schemas"]["BilanFileOut"];
export type IngestionJob = components["schemas"]["IngestionJobOut"];
export type ConsumptionResponse = components["schemas"]["ConsumptionResponse"];
export type ConsumptionPoint = components["schemas"]["ConsumptionPoint"];
export type UploadResponse = components["schemas"]["UploadResponse"];
export type TopMetric = components["schemas"]["TopMetric"];
export type Co2SeriesResponse = components["schemas"]["Co2SeriesResponse"];
export type Co2SeriesPoint = components["schemas"]["Co2SeriesPoint"];
export type Co2BreakdownResponse = components["schemas"]["Co2BreakdownResponse"];
export type Co2ForecastResponse = components["schemas"]["Co2ForecastResponse"];
export type Co2AnomaliesResponse = components["schemas"]["Co2AnomaliesResponse"];
export type Co2ModelStatus = components["schemas"]["Co2ModelStatus"];
export type Co2RetrainResponse = components["schemas"]["Co2RetrainResponse"];

export type Granularity = "10min" | "1h" | "1d";
export type JobStatus = IngestionJob["status"];

const TERMINAL_JOB_STATUSES: ReadonlyArray<string> = [
  "success",
  "partial_success",
  "failed",
];

export const queryKeys = {
  health: ["health"] as const,
  bilanFiles: (limit?: number) => ["bilan", "files", { limit }] as const,
  bilanConsumption: (params: {
    file_id?: string;
    from?: string;
    to?: string;
    granularity?: Granularity;
  }) => ["bilan", "consumption", params] as const,
  bilanTopMetrics: (limit?: number) => ["bilan", "top-metrics", { limit }] as const,
  job: (jobId: string) => ["jobs", jobId] as const,
  jobs: (filter: { type?: string; status?: string; limit?: number }) =>
    ["jobs", "list", filter] as const,
  co2Series: (params: { from?: string; to?: string; limit?: number }) =>
    ["co2", "series", params] as const,
  co2Breakdown: (params: { from?: string; to?: string }) =>
    ["co2", "breakdown", params] as const,
  co2Forecast: () => ["co2", "forecast"] as const,
  co2Anomalies: (params: { from?: string; to?: string }) =>
    ["co2", "anomalies", params] as const,
  co2Models: () => ["co2", "models"] as const,
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
    staleTime: 60 * 1000,
  });
}

export function useBilanTopMetrics(limit = 8) {
  return useQuery({
    queryKey: queryKeys.bilanTopMetrics(limit),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/bilan/top-metrics", {
        params: { query: { limit } },
      });
      if (error) throw error;
      return data!;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useBilanConsumption(params: {
  file_id?: string;
  from?: string;
  to?: string;
  granularity?: Granularity;
  enabled?: boolean;
}) {
  const { enabled = true, ...query } = params;
  return useQuery({
    queryKey: queryKeys.bilanConsumption(query),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/bilan/consumption", {
        params: { query },
      });
      if (error) throw error;
      return data!;
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecentJobs(opts: { type?: string; limit?: number } = {}) {
  const { type, limit = 5 } = opts;
  return useQuery({
    queryKey: queryKeys.jobs({ type, limit }),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs", {
        params: { query: { type, limit } },
      });
      if (error) throw error;
      return data!;
    },
    refetchInterval: 5_000,
    staleTime: 2_000,
  });
}

/** Polls a single job every 1s until it reaches a terminal state. */
export function useJob(
  jobId: string | null | undefined,
  opts?: Partial<UseQueryOptions<IngestionJob>>,
) {
  return useQuery<IngestionJob>({
    queryKey: queryKeys.job(jobId ?? "(none)"),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs/{job_id}", {
        params: { path: { job_id: jobId! } },
      });
      if (error) throw error;
      return data!;
    },
    enabled: !!jobId,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status && TERMINAL_JOB_STATUSES.includes(status) ? false : 1_000;
    },
    staleTime: 0,
    ...opts,
  });
}

/** POST /api/ingest/upload — multipart. Returns the job kickoff response. */
export function useUploadBilan() {
  const qc = useQueryClient();
  return useMutation<UploadResponse, Error, File>({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/api/ingest/upload`,
        { method: "POST", body: fd },
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`upload failed: ${res.status} ${text}`);
      }
      return (await res.json()) as UploadResponse;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["bilan", "files"] });
    },
  });
}

export function isTerminalStatus(status: string | undefined | null): boolean {
  return !!status && TERMINAL_JOB_STATUSES.includes(status);
}


// ---------------------------------------------------------------------------
// CO₂ analytics — M12
// ---------------------------------------------------------------------------

export function useCo2Series(params: { from?: string; to?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: queryKeys.co2Series(params),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/co2/series", {
        params: { query: params },
      });
      if (error) throw error;
      return data!;
    },
    staleTime: 60 * 1000,
  });
}

export function useCo2Breakdown(params: { from?: string; to?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.co2Breakdown(params),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/co2/breakdown", {
        params: { query: params },
      });
      if (error) throw error;
      return data!;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useCo2Forecast() {
  return useQuery({
    queryKey: queryKeys.co2Forecast(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/co2/forecast");
      if (error) throw error;
      return data!;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useCo2Anomalies(params: { from?: string; to?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.co2Anomalies(params),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/co2/anomalies", {
        params: { query: params },
      });
      if (error) throw error;
      return data!;
    },
    staleTime: 60 * 1000,
  });
}

export function useCo2Models() {
  return useQuery({
    queryKey: queryKeys.co2Models(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/co2/models/status");
      if (error) throw error;
      return data!;
    },
    staleTime: 60 * 1000,
  });
}

export function useCo2Retrain() {
  const qc = useQueryClient();
  return useMutation<Co2RetrainResponse, Error>({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/co2/retrain");
      if (error) throw error as unknown as Error;
      return data!;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["co2"] });
    },
  });
}
