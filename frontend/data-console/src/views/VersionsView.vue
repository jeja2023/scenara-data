<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Database, FileText, Layers3, Plus, RefreshCw } from "@lucide/vue";

import {
  api,
  createDatasetVersion,
  getDatasetVersionReference,
  listDatasetVersions,
  listDatasets,
  publishDatasetVersion,
  validateDatasetVersion,
  type DatasetRecord,
  type DatasetVersion,
  type DatasetVersionReference,
  type Page,
} from "../api";
import {
  formatTimestamp,
  labelDatasetStatus,
  labelDatasetVersionStatus,
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
const versions = ref<DatasetVersion[]>([]);
const selectedDatasetId = ref("");
const selectedVersionId = ref("");
const reference = ref<DatasetVersionReference | null>(null);

const activeTab = ref<"versions" | "datasets" | "reference">("versions");
const datasetSearch = ref("");
const versionSearch = ref("");

const form = reactive({ dataset_version_id: "", version: "" });

const selectedDataset = computed(() =>
  datasets.value.find((item) => item.dataset_id === selectedDatasetId.value) ?? null,
);
const selectedVersion = computed(() =>
  versions.value.find((item) => item.dataset_version_id === selectedVersionId.value) ?? null,
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

const datasetPagination = usePagination(filteredDatasets, 10);
const versionPagination = usePagination(filteredVersions, 10);

const tabs = computed(() => [
  {
    id: "versions",
    label: "版本治理与操作",
    icon: Layers3,
    badge: versions.value.length,
  },
  {
    id: "datasets",
    label: "所属数据集切换",
    icon: Database,
    badge: datasets.value.length,
  },
  {
    id: "reference",
    label: "版本训练授权凭证",
    icon: FileText,
    badge: reference.value ? "已生成" : undefined,
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
    const datasetPage = await listDatasets();
    datasets.value = datasetPage.items;
    if (!selectedDatasetId.value && datasets.value.length) {
      selectedDatasetId.value = datasets.value[0]?.dataset_id ?? "";
    }
    if (selectedDatasetId.value) {
      await loadVersions(selectedDatasetId.value);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "版本治理加载失败";
  } finally {
    loading.value = false;
  }
}

async function selectDataset(datasetId: string): Promise<void> {
  selectedDatasetId.value = datasetId;
  await loadVersions(datasetId);
}

async function loadVersions(datasetId: string): Promise<void> {
  if (!datasetId) {
    versions.value = [];
    reference.value = null;
    return;
  }
  const page = await listDatasetVersions(datasetId).catch(
    () => ({ items: [], total: 0, next_cursor: null }) as Page<DatasetVersion>,
  );
  versions.value = page.items;
  selectedVersionId.value = versions.value[0]?.dataset_version_id ?? "";
  if (selectedVersionId.value) {
    try {
      reference.value = await getDatasetVersionReference(selectedVersionId.value);
    } catch {
      reference.value = null;
    }
  } else {
    reference.value = null;
  }
}

async function submitVersion(): Promise<void> {
  if (!selectedDatasetId.value || !form.version.trim()) return;
  saving.value = true;
  clearFeedback();
  try {
    const created = await createDatasetVersion(selectedDatasetId.value, {
      dataset_version_id: form.dataset_version_id.trim() || undefined,
      version: form.version.trim(),
    });
    form.dataset_version_id = "";
    form.version = "";
    selectedVersionId.value = created.dataset_version_id;
    message.value = `已成功创建版本「${created.version}」`;
    await loadVersions(selectedDatasetId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "版本创建失败";
  } finally {
    saving.value = false;
  }
}

async function transition(
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
        { method: "POST", body: JSON.stringify({ status }) },
      );
      updatedStatus = response.status;
    }
    message.value = `版本状态已更新为「${labelDatasetVersionStatus(updatedStatus)}」`;
    await loadVersions(selectedDatasetId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "状态切换失败";
  } finally {
    saving.value = false;
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page versions-page">
    <div class="hero-band panel" style="margin-bottom: 16px;">
      <div>
        <p class="eyebrow">景枢数据平台 · 版本生命周期</p>
        <h2>版本治理与训练发布中枢</h2>
        <p class="hero-copy">
          当前归属数据集：
          <strong v-if="selectedDataset" style="color: var(--color-accent);">
            {{ selectedDataset.name }} ({{ selectedDataset.dataset_id }})
          </strong>
          <span v-else class="muted">未选中数据集</span>
          <span v-if="selectedVersion" class="muted">
            · 当前选中版本：<strong>{{ selectedVersion.version }}</strong> ({{ labelDatasetVersionStatus(selectedVersion.status) }})
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

    <!-- Tab 1: 版本治理与操作 -->
    <section v-if="activeTab === 'versions'" class="panel">
      <div class="panel-header">
        <h3>
          <Layers3 :size="18" />
          <span>版本创建与治理流转</span>
          <span v-if="selectedDataset" class="muted tiny">（所属数据集：{{ selectedDataset.name }}）</span>
        </h3>
        <UiSearchBox v-model="versionSearch" placeholder="搜索版本号或哈希摘要..." />
      </div>

      <!-- 创建版本表单 -->
      <div class="panel-body form-grid" style="border-bottom: 1px solid var(--line); background: var(--surface-soft);">
        <label>
          <span>版本唯一标识（可选）</span>
          <input v-model="form.dataset_version_id" placeholder="例如：dsv_20260816" />
        </label>
        <label>
          <span>语义版本号（必填）</span>
          <input v-model="form.version" placeholder="例如：1.0.0" />
        </label>
        <div class="span-2" style="display: flex; justify-content: flex-end;">
          <button
            class="button primary"
            :disabled="saving || !selectedDatasetId || !form.version.trim()"
            @click="submitVersion"
          >
            <Plus :size="16" />创建新版本
          </button>
        </div>
      </div>

      <!-- 版本表格 -->
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 220px;" />
            <col style="width: 110px;" />
            <col style="width: 100px;" />
            <col style="width: 200px;" />
            <col style="width: 180px;" />
            <col style="width: 220px;" />
          </colgroup>
          <thead>
            <tr>
              <th>语义版本 / 标识</th>
              <th>发布状态</th>
              <th>样本总数</th>
              <th>清单摘要校验和</th>
              <th>创建时间</th>
              <th>治理流转操作</th>
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
                    :disabled="saving || !['draft', 'failed'].includes(version.status)"
                    @click.stop="transition(version, 'building')"
                  >
                    构建
                  </button>
                  <button
                    class="button secondary"
                    :disabled="saving || version.status !== 'building'"
                    @click.stop="transition(version, 'ready')"
                  >
                    校验
                  </button>
                  <button
                    class="button primary"
                    :disabled="saving || version.status !== 'ready'"
                    @click.stop="transition(version, 'published')"
                  >
                    发布
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!versionPagination.paginatedItems.value.length">
              <td colspan="6" class="empty">
                {{ selectedDatasetId ? "当前数据集下暂无版本，请使用上方表单创建" : "请先切换所属数据集" }}
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

    <!-- Tab 2: 所属数据集切换 -->
    <section v-if="activeTab === 'datasets'" class="panel">
      <div class="panel-header">
        <h3><Database :size="18" /> 选择当前治理的数据集</h3>
        <UiSearchBox v-model="datasetSearch" placeholder="搜索数据集名称或 ID..." />
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 260px;" />
            <col style="width: 120px;" />
            <col />
            <col style="width: 140px;" />
          </colgroup>
          <thead>
            <tr>
              <th>名称 / 唯一标识</th>
              <th>运行状态</th>
              <th>业务描述说明</th>
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
                <div class="table-actions">
                  <button
                    class="button secondary"
                    :class="{ primary: dataset.dataset_id === selectedDatasetId }"
                    @click.stop="selectDataset(dataset.dataset_id); activeTab = 'versions'"
                  >
                    {{ dataset.dataset_id === selectedDatasetId ? "已选中" : "切换为当前" }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!datasetPagination.paginatedItems.value.length">
              <td colspan="4" class="empty">暂无匹配的数据集</td>
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

    <!-- Tab 3: 版本训练授权凭证 -->
    <section v-if="activeTab === 'reference'" class="panel">
      <div class="panel-header">
        <h3><FileText :size="18" /> 模型训练授权凭证与清单索引</h3>
        <span class="muted tiny mono">{{ selectedVersion?.version || "未选择版本" }}</span>
      </div>
      <div v-if="reference" class="panel-body">
        <dl class="kv-list">
          <div><dt>所属数据集</dt><dd class="mono">{{ reference.dataset_id }}</dd></div>
          <div><dt>语义版本号</dt><dd><strong>{{ reference.version }}</strong></dd></div>
          <div><dt>清单摘要校验和 (SHA-256)</dt><dd class="mono">{{ shortHash(reference.manifest_sha256) }}</dd></div>
          <div><dt>授权标识 (Authorization ID)</dt><dd class="mono">{{ reference.authorization_id }}</dd></div>
          <div class="span-2">
            <dt>已授权消费模型仓库 (Authorized Consumer Repositories)</dt>
            <dd>{{ reference.authorized_consumer_repository_ids.join("，") || "暂无限制" }}</dd>
          </div>
          <div class="span-2">
            <dt>凭证签发时间 (UTC+8)</dt>
            <dd>{{ formatTimestamp(reference.created_at) }}</dd>
          </div>
        </dl>
        <div style="margin-top: 14px; padding: 12px 16px; background: var(--surface-soft); border: 1px solid var(--line); border-radius: var(--radius-sm);">
          <div class="muted tiny" style="margin-bottom: 6px; font-weight: 700;">清单定位统一资源标识 (MANIFEST URI)</div>
          <div class="mono tiny" style="word-break: break-all; color: var(--color-text);">{{ reference.manifest_uri }}</div>
        </div>
      </div>
      <div v-else class="empty">
        请选择一个已发布（Published）的版本以查看其对应的模型训练引用凭证。
      </div>
    </section>
  </section>
</template>
