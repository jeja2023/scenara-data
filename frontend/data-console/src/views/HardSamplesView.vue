<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { FlaskConical, RefreshCw, Search, Upload } from "@lucide/vue";

import {
  getHardSampleImport,
  intakeHardSamples,
  listSamples,
  type HardSampleImportRecord,
  type HardSampleIntakeRequest,
  type HardSampleIntakeResponse,
  type SampleRecord,
} from "../api";
import type { HardSampleContractManifest } from "../types";
import {
  formatTimestamp,
  labelHardSampleImportStatus,
  shortHash,
} from "../labels";
import { useRefresh } from "../composables/useRefresh";

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");
const samples = ref<SampleRecord[]>([]);
const selectedSampleId = ref("");
const importIdLookup = ref("");
const latestImport = ref<HardSampleImportRecord | null>(null);

const manifestDraft = reactive({
  manifest_id: "",
  dataset_id: "",
  version: "1.0.0",
  label_schema: "scenara.feedback.correction.v1",
  split: "train" as "train" | "validation" | "test",
  created_by: "data-console",
  publish: false,
  build_version: "",
  annotation_schema_id: "",
});

const itemDraft = reactive({
  feedback_id: "",
  kind: "false_negative" as HardSampleContractManifest["items"][number]["kind"],
  media_ref: "",
  result_ref: "",
  model_id: "person-reid",
  model_version: "1.0.0",
  pipeline_id: "portrait.pipeline",
  pipeline_version: "1.0.0",
  correction: JSON.stringify({ label: "person" }, null, 2),
  authorized_for_training: true,
  deidentified: true,
});

const sourceDraft = reactive({
  bucket: "scenara-datasets",
  key: "",
  version: "",
  checksum: "",
  size_bytes: 0,
  content_type: "image/jpeg",
  source_result_id: "",
  source_resource_type: "media_asset",
  media_type: "image/jpeg",
  person_id: "",
  camera_id: "",
  bbox: "",
  dataset_split: "train" as "train" | "query" | "gallery",
  captured_at: "",
  occurred_at: new Date().toISOString(),
});

const selectedSample = computed(
  () => samples.value.find((item) => item.sample_id === selectedSampleId.value) ?? null,
);

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

function parseJson(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("correction must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function canonicalize(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return `[${value.map((item) => canonicalize(item)).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
      left.localeCompare(right),
    );
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalize(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256Hex(value: string): Promise<string> {
  const buffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(buffer)].map((item) => item.toString(16).padStart(2, "0")).join("");
}

function fillFromSample(sample: SampleRecord | null): void {
  if (!sample) return;
  itemDraft.feedback_id = sample.sample_id;
  itemDraft.media_ref = sample.source_resource_id || sample.sample_id;
  sourceDraft.bucket = sample.source_ref.bucket;
  sourceDraft.key = sample.source_ref.key;
  sourceDraft.version = sample.source_ref.version ?? "";
  sourceDraft.checksum = sample.source_ref.checksum.replace(/^sha256:/, "");
  sourceDraft.size_bytes = sample.source_ref.size_bytes;
  sourceDraft.content_type = sample.source_ref.content_type;
  sourceDraft.source_result_id = sample.source_resource_id || sample.sample_id;
  sourceDraft.media_type = sample.media_type;
  sourceDraft.person_id = sample.person_id ?? "";
  sourceDraft.camera_id = sample.camera_id ?? "";
  sourceDraft.bbox = sample.bbox?.join(",") ?? "";
  sourceDraft.dataset_split = sample.dataset_split ?? "train";
  sourceDraft.captured_at = sample.captured_at ? String(sample.captured_at) : "";
}

async function refresh(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const page = await listSamples();
    samples.value = page.items;
    if (!selectedSampleId.value && samples.value.length) {
      selectedSampleId.value = samples.value[0]?.sample_id ?? "";
    }
    if (selectedSample.value) fillFromSample(selectedSample.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "样本加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadImport(importId: string): Promise<void> {
  if (!importId) return;
  saving.value = true;
  clearFeedback();
  try {
    latestImport.value = await getHardSampleImport(importId);
    message.value = `已载入导入结果 ${importId}`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "导入记录加载失败";
  } finally {
    saving.value = false;
  }
}

async function submit(): Promise<void> {
  saving.value = true;
  clearFeedback();
  try {
    const manifestPayload = {
      schema_version: "1.0" as const,
      manifest_id: manifestDraft.manifest_id.trim(),
      tenant_id: "default",
      project_id: "default",
      dataset_id: manifestDraft.dataset_id.trim(),
      version: manifestDraft.version.trim(),
      label_schema: manifestDraft.label_schema.trim(),
      split: manifestDraft.split,
      items: [
        {
          feedback_id: itemDraft.feedback_id.trim(),
          kind: itemDraft.kind,
          media_ref: itemDraft.media_ref.trim(),
          result_ref: itemDraft.result_ref.trim(),
          model_id: itemDraft.model_id.trim(),
          model_version: itemDraft.model_version.trim(),
          pipeline_id: itemDraft.pipeline_id.trim(),
          pipeline_version: itemDraft.pipeline_version.trim(),
          correction: parseJson(itemDraft.correction),
          authorized_for_training: itemDraft.authorized_for_training,
          deidentified: itemDraft.deidentified,
        },
      ],
      sha256: "",
      created_by: manifestDraft.created_by.trim(),
      created_at: Math.floor(Date.now() / 1000),
    } as HardSampleContractManifest;
    const hash = await sha256Hex(
      canonicalize({
        schema_version: manifestPayload.schema_version,
        dataset_id: manifestPayload.dataset_id,
        version: manifestPayload.version,
        label_schema: manifestPayload.label_schema,
        split: manifestPayload.split,
        items: manifestPayload.items,
      }),
    );
    manifestPayload.sha256 = hash;
    const request: HardSampleIntakeRequest = {
      schema_version: "1.0",
      manifest: manifestPayload,
      sources: [
        {
          feedback_id: itemDraft.feedback_id.trim(),
          source_ref: {
            bucket: sourceDraft.bucket.trim(),
            key: sourceDraft.key.trim(),
            version: sourceDraft.version.trim() || null,
            checksum: `sha256:${sourceDraft.checksum.trim()}`,
            size_bytes: sourceDraft.size_bytes,
            content_type: sourceDraft.content_type.trim(),
          },
          occurred_at: sourceDraft.occurred_at,
          source_result_id: sourceDraft.source_result_id.trim() || null,
          source_resource_type: sourceDraft.source_resource_type.trim(),
          media_type: sourceDraft.media_type.trim(),
          person_id: sourceDraft.person_id.trim() || null,
          camera_id: sourceDraft.camera_id.trim() || null,
          bbox: sourceDraft.bbox.trim()
            ? (sourceDraft.bbox.split(",").map((item) => Number(item.trim())) as [number, number, number, number])
            : null,
          dataset_split: sourceDraft.dataset_split,
          captured_at: sourceDraft.captured_at.trim() || null,
        },
      ],
      annotation_schema_id: manifestDraft.annotation_schema_id.trim() || null,
      build_version: manifestDraft.build_version.trim() || null,
      publish: manifestDraft.publish,
    };
    const response = await intakeHardSamples(request);
    latestImport.value = {
      import_id: response.import_id,
      manifest_id: response.manifest_id,
      manifest_checksum: manifestPayload.sha256,
      status: response.replayed ? "succeeded" : response.status,
      accepted_count: response.accepted_count,
      rejected_count: response.rejected_count,
      skipped_count: response.skipped_count,
      sample_ids: response.sample_ids,
      annotation_task_ids: response.annotation_task_ids,
      created_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      error_code: null,
      error_message: null,
    };
    message.value = `难例清单已提交：${response.import_id}`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "难例提交失败";
  } finally {
    saving.value = false;
  }
}

watch(selectedSampleId, (value) => {
  fillFromSample(samples.value.find((item) => item.sample_id === value) ?? null);
});

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3><FlaskConical :size="18" /> 难例清单提交</h3>
          <button class="button secondary" @click="refresh"><RefreshCw :size="16" />刷新样本</button>
        </div>
        <div class="panel-body form-grid">
          <label class="span-2"><span>选择样本</span><select v-model="selectedSampleId">
            <option value="">手动填写</option>
            <option v-for="sample in samples" :key="sample.sample_id" :value="sample.sample_id">{{ sample.sample_id }} · {{ sample.media_type }}</option>
          </select></label>
          <label><span>Manifest ID</span><input v-model="manifestDraft.manifest_id" placeholder="hsm_20260816_001" /></label>
          <label><span>数据集 ID</span><input v-model="manifestDraft.dataset_id" placeholder="dst_20260816" /></label>
          <label><span>版本</span><input v-model="manifestDraft.version" placeholder="1.0.0" /></label>
          <label><span>标签 schema</span><input v-model="manifestDraft.label_schema" /></label>
          <label><span>分割</span><select v-model="manifestDraft.split"><option value="train">train</option><option value="validation">validation</option><option value="test">test</option></select></label>
          <label><span>构建版本</span><input v-model="manifestDraft.build_version" placeholder="1.0.0" /></label>
          <label><span>注解 schema</span><input v-model="manifestDraft.annotation_schema_id" placeholder="scenara.feedback.correction.v1" /></label>
          <label><span>创建者</span><input v-model="manifestDraft.created_by" /></label>
          <label class="toggle"><input v-model="manifestDraft.publish" type="checkbox" />提交后直接发布</label>
        </div>

        <div class="section-title">条目与来源</div>
        <div class="form-grid compact-grid">
          <label><span>反馈 ID</span><input v-model="itemDraft.feedback_id" /></label>
          <label><span>类型</span><select v-model="itemDraft.kind"><option value="false_positive">false_positive</option><option value="false_negative">false_negative</option><option value="wrong_attribute">wrong_attribute</option><option value="wrong_identity">wrong_identity</option><option value="ocr_correction">ocr_correction</option></select></label>
          <label><span>媒体引用</span><input v-model="itemDraft.media_ref" /></label>
          <label><span>结果引用</span><input v-model="itemDraft.result_ref" /></label>
          <label><span>模型 ID</span><input v-model="itemDraft.model_id" /></label>
          <label><span>模型版本</span><input v-model="itemDraft.model_version" /></label>
          <label><span>流水线 ID</span><input v-model="itemDraft.pipeline_id" /></label>
          <label><span>流水线版本</span><input v-model="itemDraft.pipeline_version" /></label>
          <label class="span-2"><span>纠正 JSON</span><textarea v-model="itemDraft.correction" rows="5" /></label>
          <label class="toggle"><input v-model="itemDraft.authorized_for_training" type="checkbox" />允许训练</label>
          <label class="toggle"><input v-model="itemDraft.deidentified" type="checkbox" />已脱敏</label>
        </div>

        <div class="form-grid compact-grid divider-top">
          <label><span>源桶</span><input v-model="sourceDraft.bucket" /></label>
          <label><span>源 Key</span><input v-model="sourceDraft.key" /></label>
          <label><span>版本</span><input v-model="sourceDraft.version" /></label>
          <label><span>Checksum</span><input v-model="sourceDraft.checksum" /></label>
          <label><span>大小(bytes)</span><input v-model.number="sourceDraft.size_bytes" type="number" min="0" /></label>
          <label><span>Content-Type</span><input v-model="sourceDraft.content_type" /></label>
          <label><span>source_result_id</span><input v-model="sourceDraft.source_result_id" /></label>
          <label><span>资源类型</span><input v-model="sourceDraft.source_resource_type" /></label>
          <label><span>媒体类型</span><input v-model="sourceDraft.media_type" /></label>
          <label><span>person_id</span><input v-model="sourceDraft.person_id" /></label>
          <label><span>camera_id</span><input v-model="sourceDraft.camera_id" /></label>
          <label><span>bbox</span><input v-model="sourceDraft.bbox" placeholder="1,2,30,40" /></label>
          <label><span>dataset_split</span><select v-model="sourceDraft.dataset_split"><option value="train">train</option><option value="query">query</option><option value="gallery">gallery</option></select></label>
          <label><span>captured_at</span><input v-model="sourceDraft.captured_at" placeholder="2026-08-16T12:00:00Z" /></label>
          <label class="span-2"><span>occurred_at</span><input v-model="sourceDraft.occurred_at" /></label>
        </div>

        <div class="panel-footer">
          <button class="button primary" :disabled="saving || !manifestDraft.manifest_id || !manifestDraft.dataset_id || !itemDraft.feedback_id || !sourceDraft.key" @click="submit">
            <Upload :size="16" />提交难例清单
          </button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3><Search :size="18" /> 导入结果</h3>
          <button class="button secondary" :disabled="saving || !importIdLookup.trim()" @click="loadImport(importIdLookup.trim())">查询</button>
        </div>
        <div class="panel-body form-grid">
          <label class="span-2"><span>导入 ID</span><input v-model="importIdLookup" placeholder="hsi_..." /></label>
        </div>
        <div v-if="latestImport" class="panel-body">
          <dl class="kv-list">
            <div><dt>导入 ID</dt><dd>{{ latestImport.import_id }}</dd></div>
            <div><dt>状态</dt><dd><span class="badge" :class="latestImport.status">{{ labelHardSampleImportStatus(latestImport.status) }}</span></dd></div>
            <div><dt>接收</dt><dd>{{ latestImport.accepted_count }}</dd></div>
            <div><dt>跳过</dt><dd>{{ latestImport.skipped_count }}</dd></div>
            <div><dt>失败</dt><dd>{{ latestImport.rejected_count }}</dd></div>
            <div><dt>时间</dt><dd>{{ formatTimestamp(latestImport.created_at) }}</dd></div>
          </dl>
          <div class="mini-list">
            <div>
              <span>样本</span>
              <p class="mono">{{ latestImport.sample_ids.join(', ') || '-' }}</p>
            </div>
            <div>
              <span>任务</span>
              <p class="mono">{{ latestImport.annotation_task_ids.join(', ') || '-' }}</p>
            </div>
            <div>
              <span>Manifest</span>
              <p class="mono">{{ shortHash(latestImport.manifest_checksum) }}</p>
            </div>
          </div>
          <p v-if="latestImport.error_message" class="callout error small">{{ latestImport.error_message }}</p>
        </div>
        <div v-else class="empty">提交后可在这里查看结果</div>

        <div class="panel-header subhead">
          <h4>样本池</h4>
          <span class="muted">{{ samples.length }} 条</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr><th>样本</th><th>媒体</th><th>引用</th><th>时间</th></tr></thead>
            <tbody>
              <tr v-for="sample in samples.slice(0, 10)" :key="sample.sample_id" @click="selectedSampleId = sample.sample_id">
                <td><strong>{{ sample.sample_id }}</strong><div class="mono muted">{{ sample.source_resource_id || '-' }}</div></td>
                <td>{{ sample.media_type }}</td>
                <td class="truncate">{{ sample.source_ref.bucket }}/{{ sample.source_ref.key }}</td>
                <td>{{ formatTimestamp(sample.created_at) }}</td>
              </tr>
              <tr v-if="!samples.length"><td colspan="4" class="empty">暂无样本</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </section>
</template>
