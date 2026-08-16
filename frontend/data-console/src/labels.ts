import type {
  DatasetStatus,
  DatasetVersionStatus,
  HardSampleImportStatus,
  Timestamp,
} from "./types";

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
  const units = ["B", "KiB", "MiB", "GiB"];
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

