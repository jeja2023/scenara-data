import type {
  DatasetStatus,
  DatasetVersionStatus,
  HardSampleImportStatus,
  HardSampleContractManifest,
  Timestamp,
} from "./types";

type ReadinessState = "checking" | "ready" | "offline" | "not_ready";
type PrincipalType = "user" | "service_account";
type RuntimeMode = "memory" | "postgres";
type HealthStatus = "ok" | "warning" | "error" | "unknown" | string;
type SampleSplit = "train" | "query" | "gallery" | "validation" | "test" | "unspecified";
type HardSampleKind = HardSampleContractManifest["items"][number]["kind"];

const datasetStatusLabels: Record<DatasetStatus, string> = {
  draft: "草稿",
  active: "启用",
  archived: "已归档",
};

const datasetVersionStatusLabels: Record<DatasetVersionStatus, string> = {
  draft: "草稿",
  building: "构建中",
  ready: "可发布",
  published: "已发布",
  archived: "已归档",
  failed: "失败",
};

const hardSampleImportStatusLabels: Record<HardSampleImportStatus, string> = {
  queued: "排队中",
  running: "处理中",
  succeeded: "成功",
  failed: "失败",
  cancelled: "已取消",
};

const readinessStateLabels: Record<Exclude<ReadinessState, "not_ready">, string> = {
  checking: "检查中",
  ready: "已就绪",
  offline: "离线",
};

const principalTypeLabels: Record<PrincipalType, string> = {
  user: "用户",
  service_account: "服务账号",
};

const runtimeModeLabels: Record<RuntimeMode, string> = {
  memory: "内存模式",
  postgres: "PostgreSQL 模式",
};

const maturityLabels: Record<string, string> = {
  planned: "规划中",
  seed: "起步",
  implemented: "已实现",
  qualified: "已验证",
  production_ready: "生产就绪",
};

const readinessCheckLabels: Record<string, string> = {
  repository: "数据仓库",
  object_storage: "对象存储",
  lock: "分布式锁",
};

const healthStatusLabels: Record<string, string> = {
  ok: "正常",
  warning: "警告",
  error: "错误",
  unknown: "未知",
};

const sampleSplitLabels: Record<SampleSplit, string> = {
  train: "训练集",
  query: "查询集",
  gallery: "图库集",
  validation: "验证集",
  test: "测试集",
  unspecified: "未指定",
};

const hardSampleKindLabels: Record<HardSampleKind, string> = {
  false_positive: "误报",
  false_negative: "漏报",
  wrong_attribute: "属性错误",
  wrong_identity: "身份错误",
  ocr_correction: "OCR 校正",
};

export function labelDatasetStatus(value: DatasetStatus): string {
  return datasetStatusLabels[value];
}

export function labelDatasetVersionStatus(value: DatasetVersionStatus): string {
  return datasetVersionStatusLabels[value];
}

export function labelHardSampleImportStatus(
  value: HardSampleImportStatus,
): string {
  return hardSampleImportStatusLabels[value];
}

export function labelReadinessState(value: ReadinessState): string {
  return value === "not_ready" ? "未就绪" : readinessStateLabels[value];
}

export function labelPrincipalType(value: PrincipalType): string {
  return principalTypeLabels[value];
}

export function labelRuntimeMode(value: RuntimeMode | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "未知";
  return runtimeModeLabels[value as RuntimeMode] ?? String(value);
}

export function labelMaturity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "未知";
  return maturityLabels[value] ?? String(value);
}

export function labelReadinessCheck(value: string): string {
  return readinessCheckLabels[value] ?? value;
}

export function labelHealthStatus(value: HealthStatus | null | undefined): string {
  if (!value) return "未知";
  return healthStatusLabels[value] ?? String(value);
}

export function labelSampleSplit(value: SampleSplit | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "未指定";
  return sampleSplitLabels[value as SampleSplit] ?? String(value);
}

export function labelHardSampleKind(value: HardSampleKind): string {
  return hardSampleKindLabels[value];
}

export function formatTimestamp(value: Timestamp | undefined | null): string {
  if (value === null || value === undefined || value === "") return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const units = ["字节", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function shortHash(value: string | null | undefined): string {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;
}
