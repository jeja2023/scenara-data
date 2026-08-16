import type {
  ApiErrorBody,
  DataQualityReport,
  DatasetStatus,
  DatasetManifest,
  DatasetRecord,
  DatasetVersion,
  DatasetVersionReference,
  HardSampleImportRecord,
  HardSampleIntakeRequest,
  HardSampleIntakeResponse,
  HealthResponse,
  ObjectReference,
  Page,
  PublicationResponse,
  ReadyzResponse,
  SampleRecord,
  ValidationResponse,
} from "./types";

export interface ConnectionSettings {
  apiBase: string;
  token: string;
  tenantId: string;
  projectId: string;
  principalId: string;
  principalType: "user" | "service_account";
  scopes: string;
  entitlements: string;
}

const STORAGE_KEY = "scenara.data.console.connection.v1";

const defaults: ConnectionSettings = {
  apiBase: import.meta.env.VITE_DATA_API_BASE ?? "http://127.0.0.1:8081",
  token: "scenara-data-dev-token",
  tenantId: "default",
  projectId: "default",
  principalId: "data-console",
  principalType: "service_account",
  scopes:
    "data.dataset.create,data.dataset.read,data.dataset.update,data.dataset.publish,data.dataset.archive,data.sample.create,data.sample.read,data.annotation.create,data.annotation.review,data.quality.run,data.lineage.read,data.import.execute,data.export.execute,data.hard_sample.import",
  entitlements: "scenara.data",
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId?: string,
  ) {
    super(message);
  }
}

export function loadConnection(): ConnectionSettings {
  try {
    const stored = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? "{}",
    ) as Partial<ConnectionSettings>;
    return { ...defaults, ...stored };
  } catch {
    return { ...defaults };
  }
}

export function saveConnection(value: ConnectionSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function connectionSummary(value: ConnectionSettings): string {
  const base = value.apiBase || "same-origin";
  return `${base} · ${value.tenantId}/${value.projectId}`;
}

function buildBaseUrl(connection: ConnectionSettings): string {
  return connection.apiBase.replace(/\/$/, "");
}

function buildHeaders(
  init: RequestInit,
  connection: ConnectionSettings,
): Headers {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${connection.token}`);
  headers.set("X-Scenara-Tenant-Id", connection.tenantId);
  headers.set("X-Scenara-Project-Id", connection.projectId);
  headers.set("X-Scenara-Principal-Id", connection.principalId);
  headers.set("X-Scenara-Principal-Type", connection.principalType);
  headers.set("X-Scenara-Permission-Scopes", connection.scopes);
  headers.set("X-Scenara-Product-Entitlements", connection.entitlements);
  headers.set("X-Request-Id", `data-${crypto.randomUUID()}`);
  headers.set("X-Trace-Id", crypto.randomUUID().replace(/-/g, ""));
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

function localizedHttpError(status: number, code: string): string {
  const byCode: Record<string, string> = {
    UNAUTHENTICATED: "身份认证失败或令牌无效",
    FORBIDDEN: "当前身份无权执行此操作",
    RESOURCE_NOT_FOUND: "未找到请求的资源",
    RESOURCE_CONFLICT: "资源状态冲突，请刷新后重试",
    INVALID_STATE_TRANSITION: "当前状态不允许执行此操作",
    VALIDATION_FAILED: "请求内容未通过校验",
    IDEMPOTENCY_CONFLICT: "幂等键已被不同请求占用",
    DEPENDENCY_UNAVAILABLE: "后端依赖暂时不可用",
    NETWORK_ERROR: "无法连接到服务，请检查地址和网络",
  };
  if (byCode[code]) return byCode[code];
  if (status === 404) return "未找到请求的资源";
  if (status === 403) return "当前身份无权执行此操作";
  if (status === 401) return "身份认证失败或令牌无效";
  if (status >= 500) return "服务暂时不可用，请稍后重试";
  return "请求失败，请稍后重试";
}

async function parseJson<T>(response: Response): Promise<T> {
  return (await response.json().catch(() => ({}))) as T;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 8000,
): Promise<T> {
  const connection = loadConnection();
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(`${buildBaseUrl(connection)}${path}`, {
    ...init,
    signal: init.signal ?? controller.signal,
    headers: buildHeaders(init, connection),
    cache: "no-store",
  });
  window.clearTimeout(timer);
  const body = await parseJson<T | ApiErrorBody>(response);
  if (!response.ok) {
    const error = (body as ApiErrorBody).error;
    throw new ApiError(
      response.status,
      error?.code ?? "HTTP_ERROR",
      localizedHttpError(response.status, error?.code ?? "HTTP_ERROR"),
      (body as ApiErrorBody).request_id,
    );
  }
  return body as T;
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return request<T>(path, init);
}

export async function fetchReadyz(): Promise<ReadyzResponse> {
  return request<ReadyzResponse>("/readyz");
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function listDatasets(): Promise<Page<DatasetRecord>> {
  return api<Page<DatasetRecord>>("/internal/v1/datasets?limit=200");
}

export async function getDataset(datasetId: string): Promise<DatasetRecord> {
  return api<DatasetRecord>(`/internal/v1/datasets/${encodeURIComponent(datasetId)}`);
}

export async function createDataset(body: {
  dataset_id?: string;
  name: string;
  description: string;
  metadata?: Record<string, unknown>;
}): Promise<DatasetRecord> {
  return api<DatasetRecord>("/internal/v1/datasets", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: body.dataset_id,
      name: body.name,
      description: body.description,
      metadata: body.metadata ?? {},
    }),
  });
}

export async function patchDataset(
  datasetId: string,
  body: Record<string, unknown>,
): Promise<DatasetRecord> {
  return api<DatasetRecord>(`/internal/v1/datasets/${encodeURIComponent(datasetId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function listDatasetVersions(
  datasetId: string,
): Promise<Page<DatasetVersion>> {
  return api<Page<DatasetVersion>>(
    `/internal/v1/datasets/${encodeURIComponent(datasetId)}/versions?limit=200`,
  );
}

export async function createDatasetVersion(
  datasetId: string,
  body: { version: string; dataset_version_id?: string },
): Promise<DatasetVersion> {
  return api<DatasetVersion>(
    `/internal/v1/datasets/${encodeURIComponent(datasetId)}/versions`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function transitionDatasetVersion(
  versionId: string,
  body: { status: string; rule_ids?: string[]; reason?: string },
): Promise<DatasetVersion> {
  return api<DatasetVersion>(
    `/internal/v1/dataset-versions/${encodeURIComponent(versionId)}/transition`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function validateDatasetVersion(
  versionId: string,
  ruleIds: string[] = [],
): Promise<ValidationResponse> {
  return api<ValidationResponse>(
    `/internal/v1/dataset-versions/${encodeURIComponent(versionId)}/validate`,
    {
      method: "POST",
      body: JSON.stringify({ rule_ids: ruleIds }),
    },
  );
}

export async function publishDatasetVersion(
  versionId: string,
): Promise<PublicationResponse> {
  return api<PublicationResponse>(
    `/internal/v1/dataset-versions/${encodeURIComponent(versionId)}/publish`,
    { method: "POST" },
  );
}

export async function addSampleToVersion(
  versionId: string,
  sampleId: string,
): Promise<DatasetVersion> {
  return api<DatasetVersion>(
    `/internal/v1/dataset-versions/${encodeURIComponent(versionId)}/samples`,
    {
      method: "POST",
      body: JSON.stringify({ sample_id: sampleId }),
    },
  );
}

export async function getDatasetVersionReference(
  versionId: string,
): Promise<DatasetVersionReference> {
  return api<DatasetVersionReference>(
    `/internal/v1/dataset-versions/${encodeURIComponent(versionId)}/reference`,
  );
}

export async function getDatasetVersionManifest(
  versionId: string,
): Promise<DatasetManifest> {
  return api<DatasetManifest>(
    `/internal/v1/dataset-versions/${encodeURIComponent(versionId)}/manifest`,
  );
}

export async function listSamples(): Promise<Page<SampleRecord>> {
  return api<Page<SampleRecord>>("/internal/v1/samples?limit=200");
}

export async function intakeHardSamples(
  body: HardSampleIntakeRequest,
): Promise<HardSampleIntakeResponse> {
  return api<HardSampleIntakeResponse>("/internal/v1/hard-sample-manifests", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getHardSampleImport(
  importId: string,
): Promise<HardSampleImportRecord> {
  return api<HardSampleImportRecord>(
    `/internal/v1/hard-sample-imports/${encodeURIComponent(importId)}`,
  );
}

export type {
  DataQualityReport,
  DatasetStatus,
  DatasetManifest,
  DatasetRecord,
  DatasetVersion,
  DatasetVersionReference,
  HardSampleImportRecord,
  HardSampleIntakeRequest,
  HardSampleIntakeResponse,
  HealthResponse,
  ObjectReference,
  Page,
  PublicationResponse,
  ReadyzResponse,
  SampleRecord,
  ValidationResponse,
};
