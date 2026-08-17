<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Database, Layers3, Plus, RefreshCw } from "@lucide/vue";

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

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");
const datasets = ref<DatasetRecord[]>([]);
const versions = ref<DatasetVersion[]>([]);
const selectedDatasetId = ref("");
const selectedVersionId = ref("");
const reference = ref<DatasetVersionReference | null>(null);

const form = reactive({ dataset_version_id: "", version: "" });

const selectedDataset = computed(() =>
  datasets.value.find((item) => item.dataset_id === selectedDatasetId.value) ?? null,
);
const selectedVersion = computed(() =>
  versions.value.find((item) => item.dataset_version_id === selectedVersionId.value) ?? null,
);

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
    message.value = `已创建版本 ${created.version}`;
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
    message.value = `版本已更新为 ${labelDatasetVersionStatus(updatedStatus)}`;
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
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3><Database :size="18" /> 数据集选择</h3>
          <button class="button secondary" @click="refresh"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="dataset in datasets"
                :key="dataset.dataset_id"
                :class="{ selected: dataset.dataset_id === selectedDatasetId }"
                @click="selectDataset(dataset.dataset_id)"
              >
                <td>
                  <strong>{{ dataset.name }}</strong>
                  <div class="mono muted">{{ dataset.dataset_id }}</div>
                </td>
                <td><span class="badge" :class="dataset.status">{{ labelDatasetStatus(dataset.status) }}</span></td>
                <td class="truncate">{{ dataset.description || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3><Layers3 :size="18" /> 版本创建</h3>
          <span class="muted">{{ selectedDataset?.name || '请选择数据集' }}</span>
        </div>
        <div class="panel-body form-grid">
          <label class="span-2"><span>版本标识（可选）</span><input v-model="form.dataset_version_id" placeholder="dsv_20260816" /></label>
          <label class="span-2"><span>语义版本</span><input v-model="form.version" placeholder="1.0.0" /></label>
          <button class="button primary" :disabled="saving || !selectedDatasetId || !form.version.trim()" @click="submitVersion">
            <Plus :size="16" />创建版本
          </button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>版本</th>
                <th>状态</th>
                <th>样本数</th>
                <th>摘要</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="version in versions" :key="version.dataset_version_id" :class="{ selected: version.dataset_version_id === selectedVersionId }" @click="selectedVersionId = version.dataset_version_id">
                <td>
                  <strong>{{ version.version }}</strong>
                  <div class="mono muted">{{ version.dataset_version_id }}</div>
                </td>
                <td><span class="badge" :class="version.status">{{ labelDatasetVersionStatus(version.status) }}</span></td>
                <td>{{ version.sample_count ?? 0 }}</td>
                <td class="mono truncate">{{ shortHash(version.manifest_sha256 || '') }}</td>
                <td>{{ formatTimestamp(version.created_at) }}</td>
                <td>
                  <div class="table-actions">
                    <button class="button secondary" :disabled="saving || !['draft', 'failed'].includes(version.status)" @click.stop="transition(version, 'building')">构建</button>
                    <button class="button secondary" :disabled="saving || version.status !== 'building'" @click.stop="transition(version, 'ready')">校验</button>
                    <button class="button primary" :disabled="saving || version.status !== 'ready'" @click.stop="transition(version, 'published')">发布</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!versions.length"><td colspan="6" class="empty">暂无版本</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-header">
        <h3>版本引用</h3>
        <span class="muted">{{ selectedVersion?.version || '未选择版本' }}</span>
      </div>
      <div v-if="reference" class="panel-body">
        <dl class="kv-list">
          <div><dt>数据集</dt><dd>{{ reference.dataset_id }}</dd></div>
          <div><dt>版本</dt><dd>{{ reference.version }}</dd></div>
          <div><dt>摘要</dt><dd class="mono">{{ shortHash(reference.manifest_sha256) }}</dd></div>
          <div><dt>授权</dt><dd>{{ reference.authorization_id }}</dd></div>
          <div><dt>模型仓库</dt><dd>{{ reference.authorized_consumer_repository_ids.join(', ') }}</dd></div>
          <div><dt>生成时间</dt><dd>{{ formatTimestamp(reference.created_at * 1000) }}</dd></div>
        </dl>
        <p class="muted tiny mono">{{ reference.manifest_uri }}</p>
      </div>
      <div v-else class="empty">选择已发布版本后查看训练引用</div>
    </section>
  </section>
</template>
