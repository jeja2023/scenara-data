<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  FlaskConical,
  RefreshCw,
  Search,
  Upload,
  Database,
  SlidersHorizontal,
  Zap,
  Sparkles,
  Layers,
  FileCode2,
  HardDrive,
} from "@lucide/vue";

import {
  loadConnection,
  getHardSampleImport,
  intakeHardSamples,
  listSamples,
  type HardSampleImportRecord,
  type HardSampleIntakeRequest,
  type SampleRecord,
} from "../api";
import type { HardSampleContractManifest } from "../types";
import {
  formatTimestamp,
  labelHardSampleKind,
  labelHardSampleImportStatus,
  labelSampleSplit,
  shortHash,
} from "../labels";
import { useRefresh } from "../composables/useRefresh";
import UiTabs from "../components/UiTabs.vue";
import UiPagination from "../components/UiPagination.vue";
import UiSearchBox from "../components/UiSearchBox.vue";
import { usePagination } from "../composables/usePagination";

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");
const samples = ref<SampleRecord[]>([]);
const selectedSampleId = ref("");
const importIdLookup = ref("");
const latestImport = ref<HardSampleImportRecord | null>(null);

const activeTab = ref<"intake" | "lookup" | "samples">("intake");
const sampleSearch = ref("");

// 录入模式：极简快速模式 vs 专家完整模式
const intakeMode = ref<"quick" | "expert">("quick");
// 专家模式内部子 Tab
const expertSubTab = ref<"manifest" | "correction" | "storage">("manifest");

function getBeijingNowIso(): string {
  return new Date().toISOString();
}

function generateRandomId(prefix: string): string {
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const rand = Math.random().toString(36).substring(2, 7);
  return `${prefix}_${dateStr}_${rand}`;
}

// 极简模式表单状态
const quickDraft = reactive({
  sample_id: "",
  manual_key: "",
  dataset_id: "dst_20260816",
  split: "train" as "train" | "validation" | "test",
  kind: "false_positive" as HardSampleContractManifest["items"][number]["kind"],
  reason: "现场光照阴影导致误报，经人工审校排除",
  outcome: "false_positive",
  authorized_for_training: true,
  deidentified: true,
  publish: false,
});

// 专家模式：清单元数据
const manifestDraft = reactive({
  manifest_id: generateRandomId("hsm"),
  dataset_id: "dst_20260816",
  version: "1.0.0",
  label_schema: "scenara.portrait.surveillance-review.v1",
  split: "train" as "train" | "validation" | "test",
  created_by: "scenara data",
  publish: false,
  build_version: "1.0.0",
  annotation_schema_id: "scenara.portrait.surveillance-review.v1",
});

// 专家模式：条目与模型纠正
const itemDraft = reactive({
  feedback_id: generateRandomId("fbk"),
  kind: "false_positive" as HardSampleContractManifest["items"][number]["kind"],
  media_ref: "samples/portrait/demo.jpg",
  result_ref: "res_demo_001",
  model_id: "person-reid",
  model_version: "1.0.0",
  pipeline_id: "portrait.pipeline",
  pipeline_version: "1.0.0",
  correction: JSON.stringify(
    {
      alert_id: "alt_001",
      triage_reason: "现场光照阴影导致误报，经人工审校排除",
      review_outcome: "false_positive",
    },
    null,
    2,
  ),
  domain: "portrait",
  annotation_schema_id: "scenara.portrait.surveillance-review.v1",
  authorized_for_training: true,
  deidentified: true,
});

// 专家模式：源存储与定位
const sourceDraft = reactive({
  bucket: "scenara-datasets",
  key: "samples/portrait/demo.jpg",
  version: "",
  checksum: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  size_bytes: 1048576,
  content_type: "image/jpeg",
  source_result_id: "res_demo_001",
  source_resource_type: "media_asset",
  media_type: "image/jpeg",
  person_id: "person_001",
  camera_id: "cam_gate_01",
  bbox: "120,80,340,560",
  dataset_split: "train" as "train" | "validation" | "test" | "query" | "gallery",
  captured_at: "",
  occurred_at: getBeijingNowIso(),
});

const filteredSamples = computed(() => {
  const q = sampleSearch.value.trim().toLowerCase();
  if (!q) return samples.value;
  return samples.value.filter(
    (s) =>
      s.sample_id.toLowerCase().includes(q) ||
      s.media_type.toLowerCase().includes(q) ||
      s.source_ref.bucket.toLowerCase().includes(q) ||
      s.source_ref.key.toLowerCase().includes(q),
  );
});

const samplePagination = usePagination(filteredSamples, 10);

const tabs = computed(() => [
  {
    id: "intake",
    label: "难例清单录入",
    icon: FlaskConical,
  },
  {
    id: "lookup",
    label: "导入结果查询",
    icon: Search,
    badge: latestImport.value ? "有记录" : undefined,
  },
  {
    id: "samples",
    label: "样本池浏览",
    icon: Database,
    badge: samples.value.length,
  },
]);

const expertSubTabs = computed(() => [
  {
    id: "manifest",
    label: "清单元数据",
    icon: Layers,
  },
  {
    id: "correction",
    label: "算法纠正与标注",
    icon: FileCode2,
  },
  {
    id: "storage",
    label: "源存储与定位",
    icon: HardDrive,
  },
]);

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

function parseJson(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("纠正内容必须是标准的 JSON 对象格式");
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
  quickDraft.sample_id = sample.sample_id;
  quickDraft.manual_key = sample.source_ref.key;
  quickDraft.split = (sample.dataset_split as "train" | "validation" | "test") || "train";

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

function applyPresetDemo(): void {
  const sample = samples.value[0] || null;
  if (sample) {
    fillFromSample(sample);
  } else {
    quickDraft.manual_key = "samples/portrait/demo_cam01_001.jpg";
    sourceDraft.key = "samples/portrait/demo_cam01_001.jpg";
  }
  quickDraft.dataset_id = "dst_20260816";
  quickDraft.split = "train";
  quickDraft.kind = "false_positive";
  quickDraft.reason = "雨天雨刷运动与车窗反光导致人员误检，经人工核查排除";
  quickDraft.outcome = "false_positive";
  quickDraft.authorized_for_training = true;
  quickDraft.deidentified = true;
  message.value = "已载入演示样例配置，可直接点击提交！";
}

async function refresh(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const page = await listSamples();
    samples.value = page.items;
    if (!selectedSampleId.value && samples.value.length) {
      selectedSampleId.value = samples.value[0]?.sample_id ?? "";
      fillFromSample(samples.value[0] ?? null);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "样本池加载失败";
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
    message.value = `已成功载入导入结果「${importId}」`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "导入记录查询失败";
  } finally {
    saving.value = false;
  }
}

async function submit(): Promise<void> {
  saving.value = true;
  clearFeedback();
  try {
    const connection = loadConnection();

    // 如果处于极简模式，自动同步并衍生专家底层字段
    if (intakeMode.value === "quick") {
      manifestDraft.dataset_id = quickDraft.dataset_id.trim();
      manifestDraft.split = quickDraft.split;
      manifestDraft.publish = quickDraft.publish;
      manifestDraft.manifest_id = generateRandomId("hsm");

      itemDraft.kind = quickDraft.kind;
      itemDraft.authorized_for_training = quickDraft.authorized_for_training;
      itemDraft.deidentified = quickDraft.deidentified;
      itemDraft.feedback_id = quickDraft.sample_id || generateRandomId("fbk");
      itemDraft.correction = JSON.stringify(
        {
          review_outcome: quickDraft.outcome,
          triage_reason: quickDraft.reason.trim() || "人工审校确认",
        },
        null,
        2,
      );

      if (quickDraft.sample_id) {
        const found = samples.value.find((s) => s.sample_id === quickDraft.sample_id);
        if (found) fillFromSample(found);
      } else if (quickDraft.manual_key) {
        sourceDraft.key = quickDraft.manual_key.trim();
        sourceDraft.dataset_split = quickDraft.split;
      }
    }

    const manifestPayload = {
      schema_version: "1.0" as const,
      manifest_id: manifestDraft.manifest_id.trim(),
      tenant_id: connection.tenantId,
      project_id: connection.projectId,
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
          domain: itemDraft.domain.trim() || null,
          annotation_schema_id: itemDraft.annotation_schema_id.trim() || null,
          authorized_for_training: itemDraft.authorized_for_training,
          deidentified: itemDraft.deidentified,
        },
      ],
      sha256: "",
      created_by: manifestDraft.created_by.trim(),
      created_at: new Date().toISOString(),
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
    message.value = `难例清单已顺利提交入库！导入标识：${response.import_id}`;
    activeTab.value = "lookup";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "难例提交失败";
  } finally {
    saving.value = false;
  }
}

watch(selectedSampleId, (value) => {
  if (value) {
    fillFromSample(samples.value.find((item) => item.sample_id === value) ?? null);
  }
});

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page hard-samples-page">
    <div class="hero-band panel" style="margin-bottom: 16px;">
      <div>
        <p class="eyebrow">景枢数据平台 · 难例负反馈接入</p>
        <h2>难例导入与质量校验</h2>
        <p class="hero-copy">
          接收现场排查出的误报、漏报与属性错误样本，自动完成格式契约校验与 SHA-256 签名，接入模型微调闭环。
        </p>
      </div>
      <button class="button secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" />{{ loading ? "正在同步..." : "刷新样本" }}
      </button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <!-- 一级 Tab：难例清单录入 / 导入结果查询 / 样本池浏览 -->
    <UiTabs v-model="activeTab" :tabs="tabs" />

    <!-- Tab 1: 难例清单录入 -->
    <section v-if="activeTab === 'intake'" class="panel">
      <!-- 录入模式切换器与辅助工具条 -->
      <div class="panel-header" style="background: var(--surface-soft);">
        <div style="display: flex; align-items: center; gap: 8px;">
          <div class="mode-switch-group">
            <button
              type="button"
              class="mode-switch-btn"
              :class="{ active: intakeMode === 'quick' }"
              @click="intakeMode = 'quick'"
            >
              <Zap :size="15" />
              <span>极简快速录入 (推荐)</span>
            </button>
            <button
              type="button"
              class="mode-switch-btn"
              :class="{ active: intakeMode === 'expert' }"
              @click="intakeMode = 'expert'"
            >
              <SlidersHorizontal :size="15" />
              <span>完整专家模式</span>
            </button>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <button type="button" class="button secondary" style="height: 30px; font-size: 12px;" @click="applyPresetDemo">
            <Sparkles :size="14" />一键填入演示样例
          </button>
        </div>
      </div>

      <!-- ================= 模式 1：极简快速录入（清晰 5 步） ================= -->
      <div v-if="intakeMode === 'quick'" class="panel-body" style="display: grid; gap: 18px; max-width: 860px; margin: 0 auto; padding: 24px;">
        <div class="quick-intro-banner">
          <strong>极简模式：仅需填写 5 项核心信息</strong>
          <span>其余底层协议、流水线参数、校验摘要与元数据标识将由系统自动计算与补齐。</span>
        </div>

        <!-- 1. 样本来源 -->
        <div class="quick-field-card">
          <div class="card-num">1</div>
          <div class="card-content">
            <label>
              <span class="card-title">选择难例样本来源</span>
              <select v-model="quickDraft.sample_id" @change="quickDraft.sample_id ? fillFromSample(samples.find(s => s.sample_id === quickDraft.sample_id) || null) : null">
                <option value="">-- 从样本池中选择已有样本（推荐） --</option>
                <option v-for="sample in samples" :key="sample.sample_id" :value="sample.sample_id">
                  {{ sample.sample_id }} · {{ sample.media_type }} · 桶: {{ sample.source_ref.bucket }}
                </option>
              </select>
            </label>
            <div v-if="!quickDraft.sample_id" style="margin-top: 8px;">
              <label>
                <span class="muted tiny">或者手动指定对象存储路径 (Key)：</span>
                <input v-model="quickDraft.manual_key" placeholder="例如：samples/portrait/20260816/001.jpg" />
              </label>
            </div>
          </div>
        </div>

        <!-- 2. 目标数据集 -->
        <div class="quick-field-card">
          <div class="card-num">2</div>
          <div class="card-content" style="display: grid; grid-template-columns: 1.5fr 1fr; gap: 12px;">
            <label>
              <span class="card-title">归属数据集标识 (Dataset ID)</span>
              <input v-model="quickDraft.dataset_id" placeholder="dst_20260816" />
            </label>
            <label>
              <span class="card-title">数据集切分 (Split)</span>
              <select v-model="quickDraft.split">
                <option value="train">{{ labelSampleSplit("train") }}</option>
                <option value="validation">{{ labelSampleSplit("validation") }}</option>
                <option value="test">{{ labelSampleSplit("test") }}</option>
              </select>
            </label>
          </div>
        </div>

        <!-- 3. 错误类型判定 -->
        <div class="quick-field-card">
          <div class="card-num">3</div>
          <div class="card-content">
            <label>
              <span class="card-title">难例错误判定类型 (Kind)</span>
              <select v-model="quickDraft.kind">
                <option value="false_positive">{{ labelHardSampleKind("false_positive") }} (模型检出但实际不存在目标)</option>
                <option value="false_negative">{{ labelHardSampleKind("false_negative") }} (现场存在目标但模型遗漏未检出)</option>
                <option value="wrong_attribute">{{ labelHardSampleKind("wrong_attribute") }} (目标属性/服饰/特征识别错误)</option>
                <option value="wrong_identity">{{ labelHardSampleKind("wrong_identity") }} (人员身份 ReID 匹配错误)</option>
                <option value="ocr_correction">{{ labelHardSampleKind("ocr_correction") }} (文字文本 OCR 识别错误)</option>
                <option value="action_correction">{{ labelHardSampleKind("action_correction") }} (人员动作行为判定错误)</option>
                <option value="temporal_correction">{{ labelHardSampleKind("temporal_correction") }} (视频时序区间起始点错误)</option>
              </select>
            </label>
          </div>
        </div>

        <!-- 4. 人工审校与理由 -->
        <div class="quick-field-card">
          <div class="card-num">4</div>
          <div class="card-content">
            <label>
              <span class="card-title">人工审校核查结论与纠正说明</span>
              <input
                v-model="quickDraft.reason"
                placeholder="例如：夜间雨刷运动与车窗反光导致人员误检，经人工核查排除"
              />
            </label>
          </div>
        </div>

        <!-- 5. 合规与发布选项 -->
        <div class="quick-field-card">
          <div class="card-num">5</div>
          <div class="card-content" style="display: flex; flex-wrap: wrap; gap: 24px; align-items: center; padding-top: 4px;">
            <label class="toggle">
              <input v-model="quickDraft.authorized_for_training" type="checkbox" />
              <span>允许参与模型训练</span>
            </label>
            <label class="toggle">
              <input v-model="quickDraft.deidentified" type="checkbox" />
              <span>已完成隐私脱敏处理</span>
            </label>
            <label class="toggle">
              <input v-model="quickDraft.publish" type="checkbox" />
              <span>提交后直接自动发布该版本</span>
            </label>
          </div>
        </div>

        <!-- 提交按钮 -->
        <div style="display: flex; justify-content: flex-end; margin-top: 8px;">
          <button
            class="button primary"
            style="min-width: 200px; height: 38px; font-size: 14px;"
            :disabled="saving || (!quickDraft.sample_id && !quickDraft.manual_key.trim()) || !quickDraft.dataset_id.trim()"
            @click="submit"
          >
            <Upload :size="17" />
            {{ saving ? "正在计算校验和并提交..." : "提交难例清单入库" }}
          </button>
        </div>
      </div>

      <!-- ================= 模式 2：专家完整模式（子 Tab 分布治理） ================= -->
      <div v-else class="expert-container">
        <!-- 二级子 Tab 导航 -->
        <div style="padding: 12px 18px 0;">
          <UiTabs v-model="expertSubTab" :tabs="expertSubTabs" />
        </div>

        <!-- 专家子 Tab 1: 清单元数据 -->
        <div v-if="expertSubTab === 'manifest'" class="panel-body form-grid">
          <label>
            <span>清单唯一标识 (Manifest ID)</span>
            <input v-model="manifestDraft.manifest_id" placeholder="hsm_20260816_001" />
          </label>
          <label>
            <span>目标数据集 ID (Dataset ID)</span>
            <input v-model="manifestDraft.dataset_id" placeholder="dst_20260816" />
          </label>
          <label>
            <span>数据集语义版本号 (Version)</span>
            <input v-model="manifestDraft.version" placeholder="1.0.0" />
          </label>
          <label>
            <span>标签规范模式 (Label Schema)</span>
            <input v-model="manifestDraft.label_schema" />
          </label>
          <label>
            <span>数据集切分类型 (Split)</span>
            <select v-model="manifestDraft.split">
              <option value="train">{{ labelSampleSplit("train") }}</option>
              <option value="validation">{{ labelSampleSplit("validation") }}</option>
              <option value="test">{{ labelSampleSplit("test") }}</option>
            </select>
          </label>
          <label>
            <span>构建版本号 (Build Version)</span>
            <input v-model="manifestDraft.build_version" placeholder="1.0.0" />
          </label>
          <label>
            <span>标注架构标识 (Annotation Schema ID)</span>
            <input v-model="manifestDraft.annotation_schema_id" />
          </label>
          <label>
            <span>清单创建者标识</span>
            <input v-model="manifestDraft.created_by" />
          </label>
          <div class="span-2">
            <label class="toggle">
              <input v-model="manifestDraft.publish" type="checkbox" />
              <span>提交入库后直接自动发布该版本</span>
            </label>
          </div>
        </div>

        <!-- 专家子 Tab 2: 条目信息与算法纠正 -->
        <div v-if="expertSubTab === 'correction'" class="panel-body form-grid">
          <label>
            <span>业务反馈唯一标识 (Feedback ID)</span>
            <input v-model="itemDraft.feedback_id" />
          </label>
          <label>
            <span>难例错误类型 (Kind)</span>
            <select v-model="itemDraft.kind">
              <option value="false_positive">{{ labelHardSampleKind("false_positive") }}</option>
              <option value="false_negative">{{ labelHardSampleKind("false_negative") }}</option>
              <option value="wrong_attribute">{{ labelHardSampleKind("wrong_attribute") }}</option>
              <option value="wrong_identity">{{ labelHardSampleKind("wrong_identity") }}</option>
              <option value="ocr_correction">{{ labelHardSampleKind("ocr_correction") }}</option>
              <option value="action_correction">{{ labelHardSampleKind("action_correction") }}</option>
              <option value="temporal_correction">{{ labelHardSampleKind("temporal_correction") }}</option>
              <option value="style_correction">{{ labelHardSampleKind("style_correction") }}</option>
              <option value="character_correction">{{ labelHardSampleKind("character_correction") }}</option>
              <option value="accessory_correction">{{ labelHardSampleKind("accessory_correction") }}</option>
            </select>
          </label>
          <label>
            <span>业务领域 (Domain)</span>
            <select v-model="itemDraft.domain">
              <option value="portrait">人像识别与重识别</option>
              <option value="ocr">文本识别与 OCR</option>
              <option value="behavior">动作与行为分析</option>
              <option value="fashion">服饰与人体属性</option>
            </select>
          </label>
          <label>
            <span>标注协议模式 (Annotation Schema)</span>
            <input v-model="itemDraft.annotation_schema_id" />
          </label>
          <label>
            <span>源媒体引用标识 (Media Ref)</span>
            <input v-model="itemDraft.media_ref" />
          </label>
          <label>
            <span>推理结果引用标识 (Result Ref)</span>
            <input v-model="itemDraft.result_ref" />
          </label>
          <label>
            <span>模型标识 (Model ID)</span>
            <input v-model="itemDraft.model_id" />
          </label>
          <label>
            <span>模型版本 (Model Version)</span>
            <input v-model="itemDraft.model_version" />
          </label>
          <label>
            <span>处理流水线标识 (Pipeline ID)</span>
            <input v-model="itemDraft.pipeline_id" />
          </label>
          <label>
            <span>流水线版本 (Pipeline Version)</span>
            <input v-model="itemDraft.pipeline_version" />
          </label>
          <label class="span-2">
            <span>人工审校纠正内容 (JSON 格式)</span>
            <textarea v-model="itemDraft.correction" rows="4" class="mono" />
          </label>
          <div class="span-2" style="display: flex; gap: 24px;">
            <label class="toggle">
              <input v-model="itemDraft.authorized_for_training" type="checkbox" />
              <span>合规授权：允许参与模型训练</span>
            </label>
            <label class="toggle">
              <input v-model="itemDraft.deidentified" type="checkbox" />
              <span>合规授权：已完成隐私脱敏</span>
            </label>
          </div>
        </div>

        <!-- 专家子 Tab 3: 源对象存储与定位 -->
        <div v-if="expertSubTab === 'storage'" class="panel-body form-grid">
          <label>
            <span>存储桶名称 (Bucket)</span>
            <input v-model="sourceDraft.bucket" placeholder="scenara-datasets" />
          </label>
          <label>
            <span>对象存储路径 (Key)</span>
            <input v-model="sourceDraft.key" placeholder="samples/portrait/20260816/001.jpg" />
          </label>
          <label>
            <span>对象版本标识 (Version)</span>
            <input v-model="sourceDraft.version" />
          </label>
          <label>
            <span>SHA-256 校验和 (不带 sha256: 前缀)</span>
            <input v-model="sourceDraft.checksum" class="mono" />
          </label>
          <label>
            <span>文件大小 (字节 Bytes)</span>
            <input v-model.number="sourceDraft.size_bytes" type="number" min="0" />
          </label>
          <label>
            <span>HTTP 媒体内容类型</span>
            <input v-model="sourceDraft.content_type" />
          </label>
          <label>
            <span>源结果 ID</span>
            <input v-model="sourceDraft.source_result_id" />
          </label>
          <label>
            <span>源资源类型</span>
            <input v-model="sourceDraft.source_resource_type" />
          </label>
          <label>
            <span>媒体文件类型</span>
            <input v-model="sourceDraft.media_type" />
          </label>
          <label>
            <span>数据切分归属</span>
            <select v-model="sourceDraft.dataset_split">
              <option value="train">{{ labelSampleSplit("train") }}</option>
              <option value="validation">{{ labelSampleSplit("validation") }}</option>
              <option value="test">{{ labelSampleSplit("test") }}</option>
              <option value="query">{{ labelSampleSplit("query") }}</option>
              <option value="gallery">{{ labelSampleSplit("gallery") }}</option>
            </select>
          </label>
          <label>
            <span>人员标识 (Person ID)</span>
            <input v-model="sourceDraft.person_id" />
          </label>
          <label>
            <span>摄像机标识 (Camera ID)</span>
            <input v-model="sourceDraft.camera_id" />
          </label>
          <label>
            <span>边界框坐标 BBox (x1, y1, x2, y2)</span>
            <input v-model="sourceDraft.bbox" placeholder="120, 80, 340, 560" class="mono" />
          </label>
          <label>
            <span>媒体采集时间 (UTC+8)</span>
            <input v-model="sourceDraft.captured_at" />
          </label>
          <label class="span-2">
            <span>事件发生时间 (UTC+8)</span>
            <input v-model="sourceDraft.occurred_at" />
          </label>
        </div>

        <div class="panel-footer" style="border-top: 1px solid var(--line); padding: 18px;">
          <button
            class="button primary"
            :disabled="saving || !manifestDraft.manifest_id.trim() || !manifestDraft.dataset_id.trim() || !itemDraft.feedback_id.trim() || !sourceDraft.key.trim()"
            @click="submit"
          >
            <Upload :size="16" />{{ saving ? "正在提交..." : "提交专家清单入库" }}
          </button>
        </div>
      </div>
    </section>

    <!-- Tab 2: 导入结果查询 -->
    <section v-if="activeTab === 'lookup'" class="panel">
      <div class="panel-header">
        <h3><Search :size="18" /> 历史难例导入执行结果查询</h3>
        <div style="display: flex; gap: 8px;">
          <UiSearchBox v-model="importIdLookup" placeholder="输入导入批次标识 (如 hsi_...)" width="320px" @search="loadImport" />
          <button
            class="button secondary"
            :disabled="saving || !importIdLookup.trim()"
            @click="loadImport(importIdLookup.trim())"
          >
            查询记录
          </button>
        </div>
      </div>

      <div v-if="latestImport" class="panel-body">
        <dl class="kv-list">
          <div><dt>导入批次唯一标识 (Import ID)</dt><dd class="mono">{{ latestImport.import_id }}</dd></div>
          <div><dt>处理执行状态</dt><dd><span class="badge" :class="latestImport.status">{{ labelHardSampleImportStatus(latestImport.status) }}</span></dd></div>
          <div><dt>成功接收并生成样本</dt><dd><strong class="ok">{{ latestImport.accepted_count }} 条</strong></dd></div>
          <div><dt>跳过 / 重复忽略</dt><dd>{{ latestImport.skipped_count }} 条</dd></div>
          <div><dt>校验拒绝 / 失败</dt><dd><strong :class="latestImport.rejected_count > 0 ? 'coral' : ''">{{ latestImport.rejected_count }} 条</strong></dd></div>
          <div><dt>导入记录时间 (UTC+8)</dt><dd>{{ formatTimestamp(latestImport.created_at) }}</dd></div>
        </dl>
        <div class="mini-list" style="margin-top: 14px;">
          <div>
            <span>关联样本标识清单</span>
            <p class="mono tiny">{{ latestImport.sample_ids.join("，") || "无新建样本" }}</p>
          </div>
          <div>
            <span>下发标注任务标识</span>
            <p class="mono tiny">{{ latestImport.annotation_task_ids.join("，") || "未触发标注任务" }}</p>
          </div>
          <div>
            <span>清单契约 SHA-256 摘要</span>
            <p class="mono tiny">{{ shortHash(latestImport.manifest_checksum) }}</p>
          </div>
        </div>
        <p v-if="latestImport.error_message" class="callout error small" style="margin-top: 14px;">
          {{ latestImport.error_message }}
        </p>
      </div>
      <div v-else class="empty">
        暂无查询结果。您可以在输入框中输入导入批次标识（例如以 <code>hsi_</code> 开头的编号），或在录入 Tab 中提交清单后查看实时反馈。
      </div>
    </section>

    <!-- Tab 3: 样本池浏览 -->
    <section v-if="activeTab === 'samples'" class="panel">
      <div class="panel-header">
        <h3><Database :size="18" /> 平台基础样本池目录</h3>
        <UiSearchBox v-model="sampleSearch" placeholder="搜索样本标识、存储桶或路径..." />
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 240px;" />
            <col style="width: 120px;" />
            <col style="width: 120px;" />
            <col />
            <col style="width: 180px;" />
            <col style="width: 120px;" />
          </colgroup>
          <thead>
            <tr>
              <th>样本标识 / 来源</th>
              <th>数据切分</th>
              <th>媒体格式</th>
              <th>存储定位路径</th>
              <th>采集时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="sample in samplePagination.paginatedItems.value"
              :key="sample.sample_id"
              :class="{ selected: sample.sample_id === selectedSampleId }"
              @click="selectedSampleId = sample.sample_id"
            >
              <td>
                <span class="cell-ellipsis" v-tooltip="`${sample.sample_id} (${sample.source_resource_id || '-'})`">
                  <strong>{{ sample.sample_id }}</strong>
                  <span class="mono muted"> · {{ sample.source_resource_id || "-" }}</span>
                </span>
              </td>
              <td>{{ labelSampleSplit(sample.dataset_split) }}</td>
              <td>{{ sample.media_type }}</td>
              <td>
                <span
                  class="cell-ellipsis mono"
                  v-tooltip="`${sample.source_ref.bucket}/${sample.source_ref.key}`"
                >
                  {{ sample.source_ref.bucket }}/{{ sample.source_ref.key }}
                </span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="formatTimestamp(sample.created_at)">
                  {{ formatTimestamp(sample.created_at) }}
                </span>
              </td>
              <td>
                <div class="table-actions">
                  <button
                    class="button secondary"
                    @click.stop="fillFromSample(sample); activeTab = 'intake'"
                  >
                    填入表单
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!samplePagination.paginatedItems.value.length">
              <td colspan="6" class="empty">暂无样本记录</td>
            </tr>
          </tbody>
        </table>
      </div>
      <UiPagination
        v-model:page="samplePagination.page.value"
        v-model:page-size="samplePagination.pageSize.value"
        :total="samplePagination.total.value"
      />
    </section>
  </section>
</template>

<style scoped>
.mode-switch-group {
  display: inline-flex;
  align-items: center;
  padding: 3px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  gap: 4px;
}

.mode-switch-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition-base);
}

.mode-switch-btn:hover {
  color: var(--color-text);
}

.mode-switch-btn.active {
  background: var(--color-accent);
  color: #ffffff;
  box-shadow: 0 1px 3px rgba(47, 107, 138, 0.25);
}

.quick-intro-banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  background: var(--color-accent-soft);
  border: 1px solid rgba(47, 107, 138, 0.18);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--color-accent);
}

.quick-intro-banner strong {
  font-size: 13.5px;
}

.quick-field-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 16px;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  transition: var(--transition-base);
}

.quick-field-card:hover {
  border-color: var(--line-strong);
  background: #fdfefe;
}

.card-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #ffffff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}

.card-content {
  flex: 1;
  min-width: 0;
}

.card-title {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 6px;
}

.expert-container {
  display: grid;
  gap: 0;
}
</style>
