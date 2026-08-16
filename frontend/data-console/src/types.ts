export type Timestamp = string | number;

export type DatasetStatus = "draft" | "active" | "archived";
export type DatasetVersionStatus =
  | "draft"
  | "building"
  | "ready"
  | "published"
  | "archived"
  | "failed";
export type HardSampleImportStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface Page<T> {
  items: T[];
  total: number;
  next_cursor: string | null;
}

export interface ApiErrorBody {
  request_id?: string;
  error?: { code: string; message: string; details?: unknown };
}

export interface ObjectReference {
  bucket: string;
  key: string;
  version?: string | null;
  checksum: string;
  size_bytes: number;
  content_type: string;
}

export interface DatasetRecord {
  dataset_id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  description: string;
  status: DatasetStatus;
  metadata: Record<string, unknown>;
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface DatasetVersion {
  dataset_version_id: string;
  dataset_id: string;
  version: string;
  status: DatasetVersionStatus;
  manifest_ref?: ObjectReference | null;
  created_by: string;
  created_at: Timestamp;
  published_at?: Timestamp | null;
  archived_at?: Timestamp | null;
  manifest_sha256?: string | null;
  sample_count?: number | null;
  quality_report_id?: string | null;
  lineage_snapshot_id?: string | null;
  annotation_snapshot_id?: string | null;
  failure_reason?: string | null;
}

export interface SampleRecord {
  sample_id: string;
  tenant_id: string;
  project_id: string;
  source_ref: ObjectReference;
  media_type: string;
  source_lineage: string[];
  sample_metadata: Record<string, unknown>;
  created_at: Timestamp;
  content_ref?: ObjectReference | null;
  media_kind?: string | null;
  content_sha256?: string | null;
  source_system?: string | null;
  source_resource_type?: string | null;
  source_resource_id?: string | null;
  person_id?: string | null;
  camera_id?: string | null;
  bbox?: [number, number, number, number] | null;
  dataset_split?: "train" | "query" | "gallery" | null;
  captured_at?: Timestamp | null;
}

export interface DatasetManifest {
  manifest_id: string;
  dataset_id: string;
  dataset_version_id: string;
  version: string;
  sample_ids: string[];
  split_counts: Record<string, number>;
  manifest_ref: ObjectReference;
  created_at: Timestamp;
}

export interface DataQualityReport {
  report_id: string;
  dataset_version_id: string;
  status: "passed" | "warning" | "failed";
  summary: Record<string, unknown>;
  created_at: Timestamp;
}

export interface ValidationResponse {
  dataset_version: DatasetVersion;
  quality_report: DataQualityReport;
}

export interface PublicationResponse {
  dataset_version: DatasetVersion;
  manifest: DatasetManifest;
}

export interface DatasetVersionReference {
  schema_version: "1.0";
  dataset_id: string;
  version: string;
  manifest_uri: string;
  manifest_sha256: string;
  lineage_refs: string[];
  authorization_id: string;
  authorized_consumer_repository_ids: string[];
  created_at: number;
}

export interface HardSampleContractItem {
  feedback_id: string;
  kind:
    | "false_positive"
    | "false_negative"
    | "wrong_attribute"
    | "wrong_identity"
    | "ocr_correction";
  media_ref: string;
  result_ref: string;
  model_id: string;
  model_version: string;
  pipeline_id: string;
  pipeline_version: string;
  correction: Record<string, unknown>;
  authorized_for_training: boolean;
  deidentified: boolean;
}

export interface HardSampleContractManifest {
  schema_version: "1.0";
  manifest_id: string;
  tenant_id: string;
  project_id: string;
  dataset_id: string;
  version: string;
  label_schema: string;
  split: "train" | "validation" | "test";
  items: HardSampleContractItem[];
  sha256: string;
  created_by: string;
  created_at: Timestamp;
}

export interface HardSampleSource {
  feedback_id: string;
  source_ref: ObjectReference;
  occurred_at: string;
  source_result_id?: string | null;
  source_resource_type?: string;
  media_type?: string | null;
  person_id?: string | null;
  camera_id?: string | null;
  bbox?: [number, number, number, number] | null;
  dataset_split?: "train" | "query" | "gallery" | null;
  captured_at?: string | null;
}

export interface HardSampleIntakeRequest {
  schema_version: "1.0";
  manifest: HardSampleContractManifest;
  sources: HardSampleSource[];
  annotation_schema_id?: string | null;
  build_version?: string | null;
  publish: boolean;
}

export interface HardSampleIntakeResponse {
  import_id: string;
  manifest_id: string;
  status: HardSampleImportStatus;
  accepted_count: number;
  rejected_count: number;
  skipped_count: number;
  sample_ids: string[];
  annotation_task_ids: string[];
  dataset_version_id?: string | null;
  replayed: boolean;
}

export interface HardSampleImportRecord {
  import_id: string;
  manifest_id: string;
  manifest_checksum: string;
  status: HardSampleImportStatus;
  accepted_count: number;
  rejected_count: number;
  skipped_count: number;
  sample_ids: string[];
  annotation_task_ids: string[];
  created_at: Timestamp;
  completed_at?: Timestamp | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface ReadyzResponse {
  status: "ready" | "not_ready";
  service: string;
  runtime_mode: string;
  checks: Record<string, boolean>;
  timestamp: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  maturity: string;
  runtime_mode: string;
  timestamp: string;
}
