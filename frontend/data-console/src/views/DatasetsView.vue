<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Database, FileText, Layers3, Plus, RefreshCw, Sparkles, CheckCircle2 } from "@lucide/vue";

import {
  addSampleToVersion,
  api,
  createDataset,
  createDatasetVersion,
  getDatasetVersionReference,
  listDatasetVersions,
  listDatasets,
  listSamples,
  patchDataset,
  publishDatasetVersion,
  validateDatasetVersion,
  type DatasetRecord,
  type DatasetStatus,
  type DatasetVersion,
  type DatasetVersionReference,
  type Page,
  type SampleRecord,
} from "../api";
import {
  formatTimestamp,
  labelDatasetStatus,
  labelDatasetVersionStatus,
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
const datasets = ref<DatasetRecord[]>([]);
const samples = ref<SampleRecord[]>([]);
const versions = ref<DatasetVersion[]>([]);
const selectedDatasetId = ref("");
const selectedVersionId = ref("");
const selectedSamples = ref<string[]>([]);
const manifestReference = ref<DatasetVersionReference | null>(null);

const activeTab = ref<"datasets" | "versions" | "samples" | "reference">("datasets");
const datasetSearch = ref("");
const versionSearch = ref("");
const sampleSearch = ref("");

const datasetForm = reactive({
  dataset_id: "",
  name: "",
  description: "",
});

const versionForm = reactive({
  dataset_version_id: "",
  version: "",
});

const datasetMap = computed(() => new Map(datasets.value.map((item) => [item.dataset_id, item])));
const selectedDataset = computed(
  () => datasetMap.value.get(selectedDatasetId.value) ?? null,
);
const selectedVersion = computed(
  () => versions.value.find((item) => item.dataset_version_id === selectedVersionId.value) ?? null,
);

const filteredDatasets = computed(() => {
  const q = datasetSearch.value.trim().toLowerCase();
  if (!q) return datasets.value;
  return datasets.value.filter(
    (d) =>
      d.name.toLowerCase().includes(q) ||
      d.dataset_id.toLowerCase().includes(q) ||
      (d.description && d.description.toLowerCase().includes(q)),
  );
});

const filteredVersions = computed(() => {
  const q = versionSearch.value.trim().toLowerCase();
  if (!q) return versions.value;
  return versions.value.filter(
    (v) =>
      v.version.toLowerCase().includes(q) ||
      v.dataset_version_id.toLowerCase().includes(q) ||
      (v.manifest_sha256 && v.manifest_sha256.toLowerCase().includes(q)),
  );
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

const datasetPagination = usePagination(filteredDatasets, 10);
const versionPagination = usePagination(filteredVersions, 10);
const samplePagination = usePagination(filteredSamples, 10);

const tabs = computed(() => [
  {
    id: "datasets",
    label: "数据集目录",
    icon: Database,
    badge: datasets.value.length,
  },
  {
    id: "versions",
    label: "版本治理",
    icon: Layers3,
    badge: versions.value.length,
  },
  {
    id: "samples",
    label: "样本池关联",
    icon: Sparkles,
    badge: samples.value.length,
  },
  {
    id: "reference",
    label: "版本训练引用",
    icon: FileText,
    badge: manifestReference.value ? "已生成" : undefined,
  },
]);

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

async function refresh(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const [datasetPage, samplePage] = await Promise.all([
      listDatasets(),
      listSamples(),
    ]);
    datasets.value = datasetPage.items;
    samples.value = samplePage.items;
    if (!selectedDatasetId.value && datasets.value.length) {
      selectedDatasetId.value = datasets.value[0]?.dataset_id ?? "";
    }
    if (selectedDatasetId.value) {
      await loadVersions(selectedDatasetId.value);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "数据集加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadVersions(datasetId: string): Promise<void> {
  if (!datasetId) {
    versions.value = [];
    manifestReference.value = null;
    return;
  }
  const page = await listDatasetVersions(datasetId).catch(
    () => ({ items: [], total: 0, next_cursor: null }) as Page<DatasetVersion>,
  );
  versions.value = page.items;
  selectedVersionId.value = versions.value[0]?.dataset_version_id ?? "";
  if (selectedVersionId.value) {
    try {
      manifestReference.value = await getDatasetVersionReference(selectedVersionId.value);
    } catch {
      manifestReference.value = null;
    }
  } else {
    manifestReference.value = null;
  }
}

async function selectDataset(datasetId: string): Promise<void> {
  selectedDatasetId.value = datasetId;
  versionForm.dataset_version_id = "";
  await loadVersions(datasetId);
}

async function submitDataset(): Promise<void> {
  if (!datasetForm.name.trim()) return;
  saving.value = true;
  clearFeedback();
  try {
    const created = await createDataset({
      dataset_id: datasetForm.dataset_id.trim() || undefined,
      name: datasetForm.name.trim(),
      description: datasetForm.description.trim(),
    });
    datasetForm.dataset_id = "";
    datasetForm.name = "";
    datasetForm.description = "";
    message.value = `已成功创建数据集「${created.name}」`;
    selectedDatasetId.value = created.dataset_id;
    await refresh();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "创建数据集失败";
  } finally {
    saving.value = false;
  }
}

async function submitVersion(): Promise<void> {
  if (!selectedDatasetId.value || !versionForm.version.trim()) return;
  saving.value = true;
  clearFeedback();
  try {
    const created = await createDatasetVersion(selectedDatasetId.value, {
      dataset_version_id: versionForm.dataset_version_id.trim() || undefined,
      version: versionForm.version.trim(),
    });
    versionForm.dataset_version_id = "";
    versionForm.version = "";
    selectedVersionId.value = created.dataset_version_id;
    message.value = `已成功创建版本「${created.version}」`;
    await loadVersions(selectedDatasetId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "创建版本失败";
  } finally {
    saving.value = false;
  }
}

async function transitionVersion(
  version: DatasetVersion,
  status: "building" | "ready" | "published" | "archived" | "failed",
): Promise<void> {
  saving.value = true;
  clearFeedback();
  try {
    let updatedStatus: DatasetVersion["status"] = status;
    if (status === "ready") {
      const response = await validateDatasetVersion(version.dataset_version_id);
      updatedStatus = response.dataset_version.status;
    } else if (status === "published") {
      const response = await publishDatasetVersion(version.dataset_version_id);
      updatedStatus = response.dataset_version.status;
    } else {
      const response = await api<DatasetVersion>(
        `/internal/v1/dataset-versions/${encodeURIComponent(version.dataset_version_id)}/transition`,
        {
          method: "POST",
          body: JSON.stringify({ status }),
        },
      );
      updatedStatus = response.status;
    }
    message.value = `版本状态已更新为「${labelDatasetVersionStatus(updatedStatus)}」`;
    await loadVersions(selectedDatasetId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "版本状态更新失败";
  } finally {
    saving.value = false;
  }
}

async function addSelectedSampleToVersion(): Promise<void> {
  if (!selectedVersionId.value || !selectedSamples.value.length) return;
  saving.value = true;
  clearFeedback();
  try {
    for (const sampleId of selectedSamples.value) {
      await addSampleToVersion(selectedVersionId.value, sampleId);
    }
    const count = selectedSamples.value.length;
    selectedSamples.value = [];
    message.value = `已将选中的 ${count} 条样本加入当前版本`;
    await loadVersions(selectedDatasetId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "添加样本失败";
  } finally {
    saving.value = false;
  }
}

function selectAllCurrentPageSamples(): void {
  const currentIds = samplePagination.paginatedItems.value.map((s) => s.sample_id);
  const allSelected = currentIds.every((id) => selectedSamples.value.includes(id));
  if (allSelected) {
    selectedSamples.value = selectedSamples.value.filter((id) => !currentIds.includes(id));
  } else {
    const combined = new Set([...selectedSamples.value, ...currentIds]);
    selectedSamples.value = Array.from(combined);
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page dataset-page">
    <div class="hero-band panel" style="margin-bottom: 16px;">
      <div>
        <p class="eyebrow">景枢数据平台 · 核心资产治理</p>
        <h2>数据集与版本生命周期管理</h2>
        <p class="hero-copy">
          当前选中数据集：
          <strong v-if="selectedDataset" style="color: var(--color-accent);">
            {{ selectedDataset.name }} ({{ selectedDataset.dataset_id }})
          </strong>
          <span v-else class="muted">尚未选择</span>
          <span v-if="selectedVersion" class="muted">
            · 当前版本：<strong>{{ selectedVersion.version }}</strong> ({{ labelDatasetVersionStatus(selectedVersion.status) }})
          </span>
        </p>
      </div>
      <button class="button secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" />{{ loading ? "正在同步..." : "刷新数据" }}
      </button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <!-- 区域切换 Tab 按钮组 -->
    <UiTabs v-model="activeTab" :tabs="tabs" />

    <!-- Tab 1: 数据集目录 -->
    <section v-if="activeTab === 'datasets'" class="panel">
      <div class="panel-header">
        <h3><Database :size="18" /> 数据集资产列表</h3>
        <UiSearchBox v-model="datasetSearch" placeholder="搜索数据集名称或 ID..." />
      </div>

      <!-- 创建数据集轻量表单 -->
      <div class="panel-body form-grid" style="border-bottom: 1px solid var(--line); background: var(--surface-soft);">
        <label>
          <span>数据集标识（可选，留空将自动生成）</span>
          <input v-model="datasetForm.dataset_id" placeholder="例如：dst_20260816" />
        </label>
        <label>
          <span>数据集名称（必填）</span>
          <input v-model="datasetForm.name" placeholder="例如：园区行人重识别样本集" />
        </label>
        <label class="span-2">
          <span>数据集描述说明</span>
          <textarea v-model="datasetForm.description" rows="2" placeholder="描述该数据集的业务场景、授权范围及适用模型算法..." />
        </label>
        <div class="span-2" style="display: flex; justify-content: flex-end;">
          <button
            class="button primary"
            :disabled="saving || !datasetForm.name.trim()"
            @click="submitDataset"
          >
            <Plus :size="16" />创建新数据集
          </button>
        </div>
      </div>

      <!-- 数据集表格 -->
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 260px;" />
            <col style="width: 110px;" />
            <col />
            <col style="width: 190px;" />
            <col style="width: 120px;" />
          </colgroup>
          <thead>
            <tr>
              <th>名称 / 唯一标识</th>
              <th>运行状态</th>
              <th>业务描述</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="dataset in datasetPagination.paginatedItems.value"
              :key="dataset.dataset_id"
              :class="{ selected: dataset.dataset_id === selectedDatasetId }"
              @click="selectDataset(dataset.dataset_id)"
            >
              <td>
                <span class="cell-ellipsis" v-tooltip="`${dataset.name} (${dataset.dataset_id})`">
                  <strong>{{ dataset.name }}</strong>
                  <span class="mono muted"> · {{ dataset.dataset_id }}</span>
                </span>
              </td>
              <td>
                <span class="badge" :class="dataset.status">{{ labelDatasetStatus(dataset.status) }}</span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="dataset.description || '暂无说明'">
                  {{ dataset.description || "-" }}
                </span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="formatTimestamp(dataset.updated_at)">
                  {{ formatTimestamp(dataset.updated_at) }}
                </span>
              </td>
              <td>
                <div class="table-actions">
                  <button
                    class="button secondary"
                    :class="{ primary: dataset.dataset_id === selectedDatasetId }"
                    @click.stop="selectDataset(dataset.dataset_id); activeTab = 'versions'"
                  >
                    {{ dataset.dataset_id === selectedDatasetId ? "治理版本" : "选中治理" }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!datasetPagination.paginatedItems.value.length">
              <td colspan="5" class="empty">暂无匹配的数据集资产</td>
            </tr>
          </tbody>
        </table>
      </div>
      <UiPagination
        v-model:page="datasetPagination.page.value"
        v-model:page-size="datasetPagination.pageSize.value"
        :total="datasetPagination.total.value"
      />
    </section>

    <!-- Tab 2: 版本治理 -->
    <section v-if="activeTab === 'versions'" class="panel">
      <div class="panel-header">
        <h3>
          <Layers3 :size="18" />
          <span>版本治理列表</span>
          <span v-if="selectedDataset" class="muted tiny">
            （所属数据集：<strong>{{ selectedDataset.name }}</strong>）
          </span>
        </h3>
        <UiSearchBox v-model="versionSearch" placeholder="搜索版本号或哈希..." />
      </div>

      <!-- 创建版本表单 -->
      <div class="panel-body form-grid" style="border-bottom: 1px solid var(--line); background: var(--surface-soft);">
        <label>
          <span>版本标识（可选）</span>
          <input v-model="versionForm.dataset_version_id" placeholder="例如：dsv_20260816" />
        </label>
        <label>
          <span>语义版本号（必填）</span>
          <input v-model="versionForm.version" placeholder="例如：1.0.0" />
        </label>
        <div class="span-2" style="display: flex; justify-content: flex-end; gap: 8px;">
          <button
            class="button secondary"
            :disabled="saving || !selectedVersion || !['draft', 'failed'].includes(selectedVersion.status)"
            @click="transitionVersion(selectedVersion!, 'building')"
          >
            进入构建中
          </button>
          <button
            class="button primary"
            :disabled="saving || !selectedDatasetId || !versionForm.version.trim()"
            @click="submitVersion"
          >
            <Plus :size="16" />创建新版本
          </button>
        </div>
      </div>

      <!-- 版本列表表格 -->
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 220px;" />
            <col style="width: 110px;" />
            <col style="width: 100px;" />
            <col style="width: 190px;" />
            <col style="width: 180px;" />
            <col style="width: 220px;" />
          </colgroup>
          <thead>
            <tr>
              <th>语义版本 / 标识</th>
              <th>发布状态</th>
              <th>包含样本</th>
              <th>清单摘要校验和</th>
              <th>创建时间</th>
              <th>治理操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="version in versionPagination.paginatedItems.value"
              :key="version.dataset_version_id"
              :class="{ selected: version.dataset_version_id === selectedVersionId }"
              @click="selectedVersionId = version.dataset_version_id"
            >
              <td>
                <span class="cell-ellipsis" v-tooltip="`${version.version} (${version.dataset_version_id})`">
                  <strong>{{ version.version }}</strong>
                  <span class="mono muted"> · {{ version.dataset_version_id }}</span>
                </span>
              </td>
              <td>
                <span class="badge" :class="version.status">{{ labelDatasetVersionStatus(version.status) }}</span>
              </td>
              <td>{{ version.sample_count ?? 0 }} 条</td>
              <td>
                <span class="cell-ellipsis mono" v-tooltip="version.manifest_sha256 || '-'">
                  {{ shortHash(version.manifest_sha256 || "") }}
                </span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="formatTimestamp(version.created_at)">
                  {{ formatTimestamp(version.created_at) }}
                </span>
              </td>
              <td>
                <div class="table-actions">
                  <button
                    class="button secondary"
                    :disabled="saving || version.status !== 'building'"
                    @click.stop="transitionVersion(version, 'ready')"
                  >
                    校验
                  </button>
                  <button
                    class="button primary"
                    :disabled="saving || version.status !== 'ready'"
                    @click.stop="transitionVersion(version, 'published')"
                  >
                    发布
                  </button>
                  <button
                    class="button secondary"
                    :disabled="saving || version.status !== 'published'"
                    @click.stop="transitionVersion(version, 'archived')"
                  >
                    归档
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!versionPagination.paginatedItems.value.length">
              <td colspan="6" class="empty">
                {{ selectedDatasetId ? "当前数据集下暂无版本，可使用上方表单创建" : "请先在数据集目录中选择一个数据集" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <UiPagination
        v-model:page="versionPagination.page.value"
        v-model:page-size="versionPagination.pageSize.value"
        :total="versionPagination.total.value"
      />
    </section>

    <!-- Tab 3: 样本池关联 -->
    <section v-if="activeTab === 'samples'" class="panel">
      <div class="panel-header">
        <h3>
          <Sparkles :size="18" />
          <span>样本池浏览与关联</span>
          <span class="muted tiny">（已选中 {{ selectedSamples.length }} 项）</span>
        </h3>
        <div style="display: flex; align-items: center; gap: 8px;">
          <UiSearchBox v-model="sampleSearch" placeholder="搜索样本标识、存储桶或路径..." />
          <button
            class="button secondary"
            :disabled="saving || !selectedVersionId || !selectedSamples.length"
            @click="addSelectedSampleToVersion"
          >
            选入当前版本
          </button>
        </div>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 50px;" />
            <col style="width: 240px;" />
            <col style="width: 110px;" />
            <col style="width: 120px;" />
            <col />
            <col style="width: 180px;" />
          </colgroup>
          <thead>
            <tr>
              <th style="text-align: center;">
                <input
                  type="checkbox"
                  style="width: 16px; height: 16px; margin: 0 auto;"
                  title="全选/反选本页"
                  @change="selectAllCurrentPageSamples"
                />
              </th>
              <th>样本标识 / 来源</th>
              <th>数据切分</th>
              <th>媒体格式</th>
              <th>存储定位路径</th>
              <th>入库时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sample in samplePagination.paginatedItems.value" :key="sample.sample_id">
              <td style="text-align: center;">
                <input
                  v-model="selectedSamples"
                  :value="sample.sample_id"
                  type="checkbox"
                  style="width: 16px; height: 16px; margin: 0 auto;"
                />
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="`${sample.sample_id} (${sample.source_resource_id || '原始样本'})`">
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
            </tr>
            <tr v-if="!samplePagination.paginatedItems.value.length">
              <td colspan="6" class="empty">暂无匹配的样本数据</td>
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

    <!-- Tab 4: 版本训练引用 -->
    <section v-if="activeTab === 'reference'" class="panel">
      <div class="panel-header">
        <h3>
          <FileText :size="18" />
          <span>模型训练消费授权与 Manifest 凭证</span>
        </h3>
        <span class="muted tiny mono">{{ manifestReference?.authorization_id || "尚未生成授权凭证" }}</span>
      </div>
      <div v-if="manifestReference" class="panel-body">
        <dl class="kv-list">
          <div><dt>所属数据集</dt><dd class="mono">{{ manifestReference.dataset_id }}</dd></div>
          <div><dt>语义版本号</dt><dd><strong>{{ manifestReference.version }}</strong></dd></div>
          <div><dt>清单摘要校验和 (SHA-256)</dt><dd class="mono">{{ shortHash(manifestReference.manifest_sha256) }}</dd></div>
          <div><dt>全局授权标识 (Authorization ID)</dt><dd class="mono">{{ manifestReference.authorization_id }}</dd></div>
          <div class="span-2">
            <dt>已授权消费模型仓库 (Authorized Consumer Repositories)</dt>
            <dd>{{ manifestReference.authorized_consumer_repository_ids.join("，") || "暂无限制" }}</dd>
          </div>
          <div class="span-2">
            <dt>凭证生成时间 (UTC+8)</dt>
            <dd>{{ formatTimestamp(manifestReference.created_at) }}</dd>
          </div>
        </dl>
        <div style="margin-top: 14px; padding: 12px 16px; background: var(--surface-soft); border: 1px solid var(--line); border-radius: var(--radius-sm);">
          <div class="muted tiny" style="margin-bottom: 6px; font-weight: 700;">清单定位统一资源标识 (MANIFEST URI)</div>
          <div class="mono tiny" style="word-break: break-all; color: var(--color-text);">{{ manifestReference.manifest_uri }}</div>
        </div>
      </div>
      <div v-else class="empty">
        请在版本治理中选中一个已发布的版本以查看对应的模型训练清单授权凭证。
      </div>
    </section>
  </section>
</template>
