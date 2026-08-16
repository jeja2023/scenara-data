<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Database, Layers3, Plus, RefreshCw } from "@lucide/vue";

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
  type ObjectReference,
  type Page,
  type SampleRecord,
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
const samples = ref<SampleRecord[]>([]);
const versions = ref<DatasetVersion[]>([]);
const selectedDatasetId = ref("");
const selectedVersionId = ref("");
const selectedSamples = ref<string[]>([]);
const manifestReference = ref<Awaited<ReturnType<typeof getDatasetVersionReference>> | null>(null);

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
    message.value = `已创建数据集 ${created.name}`;
    await refresh();
    selectedDatasetId.value = created.dataset_id;
    await loadVersions(created.dataset_id);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "创建数据集失败";
  } finally {
    saving.value = false;
  }
}

async function toggleDatasetStatus(dataset: DatasetRecord, next: DatasetStatus): Promise<void> {
  saving.value = true;
  clearFeedback();
  try {
    await patchDataset(dataset.dataset_id, { status: next });
    message.value = `已更新 ${dataset.name} 状态`;
    await refresh();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "更新数据集失败";
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
    message.value = `已创建版本 ${created.version}`;
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
    if (status === "ready") {
      await validateDatasetVersion(version.dataset_version_id);
    } else if (status === "published") {
      await publishDatasetVersion(version.dataset_version_id);
    } else {
      await api<DatasetVersion>(
        `/internal/v1/dataset-versions/${encodeURIComponent(version.dataset_version_id)}/transition`,
        {
          method: "POST",
          body: JSON.stringify({ status }),
        },
      );
    }
    message.value = `版本状态已切换为 ${labelDatasetVersionStatus(status)}`;
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
    selectedSamples.value = [];
    message.value = "样本已加入版本";
    await loadVersions(selectedDatasetId.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "添加样本失败";
  } finally {
    saving.value = false;
  }
}

watch(selectedDatasetId, async (datasetId) => {
  if (datasetId) await loadVersions(datasetId);
});

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page dataset-page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3><Database :size="18" /> 数据集目录</h3>
          <button class="button secondary" @click="refresh"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="panel-body form-grid">
          <label class="span-2">
            <span>数据集 ID（可选）</span>
            <input v-model="datasetForm.dataset_id" placeholder="dst_20260816" />
          </label>
          <label class="span-2">
            <span>名称</span>
            <input v-model="datasetForm.name" placeholder="园区行人样本集" />
          </label>
          <label class="span-2">
            <span>说明</span>
            <textarea v-model="datasetForm.description" rows="3" placeholder="描述数据来源、授权边界和用途" />
          </label>
          <button class="button primary" :disabled="saving || !datasetForm.name.trim()" @click="submitDataset">
            <Plus :size="16" />创建数据集
          </button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>说明</th>
                <th>更新时间</th>
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
                <td class="truncate">{{ dataset.description || "-" }}</td>
                <td>{{ formatTimestamp(dataset.updated_at) }}</td>
              </tr>
              <tr v-if="!datasets.length"><td colspan="4" class="empty">暂无数据集</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3><Layers3 :size="18" /> 版本治理</h3>
          <span class="muted">{{ selectedDataset?.name || '请先选择数据集' }}</span>
        </div>
        <div class="panel-body form-grid">
          <label class="span-2">
            <span>版本标识（可选）</span>
            <input v-model="versionForm.dataset_version_id" placeholder="dsv_20260816" />
          </label>
          <label class="span-2">
            <span>语义版本</span>
            <input v-model="versionForm.version" placeholder="1.0.0" />
          </label>
          <button class="button primary" :disabled="saving || !selectedDatasetId || !versionForm.version.trim()" @click="submitVersion">
            <Plus :size="16" />创建版本
          </button>
          <button class="button secondary" :disabled="saving || !selectedVersion" @click="transitionVersion(selectedVersion!, 'building')">进入构建</button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>版本</th>
                <th>状态</th>
                <th>样本</th>
                <th>摘要</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="version in versions"
                :key="version.dataset_version_id"
                :class="{ selected: version.dataset_version_id === selectedVersionId }"
                @click="selectedVersionId = version.dataset_version_id"
              >
                <td>
                  <strong>{{ version.version }}</strong>
                  <div class="mono muted">{{ version.dataset_version_id }}</div>
                </td>
                <td><span class="badge" :class="version.status">{{ labelDatasetVersionStatus(version.status) }}</span></td>
                <td>{{ version.sample_count ?? 0 }}</td>
                <td class="mono truncate">{{ shortHash(version.manifest_sha256 || '') }}</td>
                <td>
                  <div class="table-actions">
                    <button class="button secondary" :disabled="saving || version.status === 'published'" @click.stop="transitionVersion(version, 'ready')">校验</button>
                    <button class="button primary" :disabled="saving || version.status !== 'ready'" @click.stop="transitionVersion(version, 'published')">发布</button>
                    <button class="button secondary" :disabled="saving || version.status === 'archived'" @click.stop="transitionVersion(version, 'archived')">归档</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!versions.length"><td colspan="5" class="empty">暂无版本</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3>样本池</h3>
          <span class="muted">{{ samples.length }} 条</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th></th>
                <th>样本</th>
                <th>类型</th>
                <th>来源</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="sample in samples.slice(0, 12)" :key="sample.sample_id">
                <td><input v-model="selectedSamples" :value="sample.sample_id" type="checkbox" /></td>
                <td>
                  <strong>{{ sample.sample_id }}</strong>
                  <div class="mono muted">{{ sample.source_resource_id || sample.source_system || 'source' }}</div>
                </td>
                <td>{{ sample.media_type }}</td>
                <td>{{ sample.source_ref.bucket }}/{{ sample.source_ref.key }}</td>
                <td>{{ formatTimestamp(sample.created_at) }}</td>
              </tr>
              <tr v-if="!samples.length"><td colspan="5" class="empty">暂无样本</td></tr>
            </tbody>
          </table>
        </div>
        <div class="panel-footer">
          <button class="button secondary" :disabled="saving || !selectedVersionId || !selectedSamples.length" @click="addSelectedSampleToVersion">
            选中样本加入当前版本
          </button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>版本引用</h3>
          <span class="muted">{{ manifestReference?.authorization_id || '未生成' }}</span>
        </div>
        <div class="panel-body" v-if="manifestReference">
          <dl class="kv-list">
            <div><dt>数据集</dt><dd>{{ manifestReference.dataset_id }}</dd></div>
            <div><dt>版本</dt><dd>{{ manifestReference.version }}</dd></div>
            <div><dt>摘要</dt><dd class="mono">{{ shortHash(manifestReference.manifest_sha256) }}</dd></div>
            <div><dt>授权</dt><dd>{{ manifestReference.authorization_id }}</dd></div>
            <div><dt>模型仓库</dt><dd>{{ manifestReference.authorized_consumer_repository_ids.join(', ') }}</dd></div>
            <div><dt>生成时间</dt><dd>{{ formatTimestamp(manifestReference.created_at * 1000) }}</dd></div>
          </dl>
          <p class="muted tiny">{{ manifestReference.manifest_uri }}</p>
        </div>
        <div v-else class="empty">选择一个已发布版本后可查看训练引用</div>
      </section>
    </div>
  </section>
</template>
