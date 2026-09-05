<script setup lang="ts">
import { computed } from "vue";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "@lucide/vue";

const props = withDefaults(
  defineProps<{
    total: number;
    page: number;
    pageSize?: number;
    pageSizeOptions?: number[];
  }>(),
  {
    pageSize: 10,
    pageSizeOptions: () => [10, 20, 50],
  },
);

const emit = defineEmits<{
  (e: "update:page", page: number): void;
  (e: "update:pageSize", size: number): void;
}>();

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)));

const fromIndex = computed(() => {
  if (props.total === 0) return 0;
  return (props.page - 1) * props.pageSize + 1;
});

const toIndex = computed(() => Math.min(props.total, props.page * props.pageSize));

function goToPage(target: number): void {
  const bounded = Math.max(1, Math.min(totalPages.value, target));
  if (bounded !== props.page) {
    emit("update:page", bounded);
  }
}

function handleSizeChange(event: Event): void {
  const target = event.target as HTMLSelectElement;
  const newSize = Number(target.value);
  emit("update:pageSize", newSize);
  emit("update:page", 1);
}
</script>

<template>
  <div class="ui-pagination" aria-label="表格分页导航">
    <div class="pagination-info">
      <span>共 <strong>{{ total }}</strong> 条记录</span>
      <span v-if="total > 0" class="pagination-range">
        （当前显示第 {{ fromIndex }} 至 {{ toIndex }} 条）
      </span>
    </div>

    <div class="pagination-controls">
      <div class="pagination-size">
        <span>每页</span>
        <select :value="pageSize" @change="handleSizeChange">
          <option v-for="opt in pageSizeOptions" :key="opt" :value="opt">
            {{ opt }} 条
          </option>
        </select>
      </div>

      <div class="pagination-buttons">
        <button
          type="button"
          class="page-btn"
          title="第一页"
          :disabled="page <= 1"
          @click="goToPage(1)"
        >
          <ChevronsLeft :size="15" />
        </button>
        <button
          type="button"
          class="page-btn"
          title="上一页"
          :disabled="page <= 1"
          @click="goToPage(page - 1)"
        >
          <ChevronLeft :size="15" />
          <span>上一页</span>
        </button>

        <span class="page-indicator">
          第 <strong>{{ page }}</strong> / {{ totalPages }} 页
        </span>

        <button
          type="button"
          class="page-btn"
          title="下一页"
          :disabled="page >= totalPages"
          @click="goToPage(page + 1)"
        >
          <span>下一页</span>
          <ChevronRight :size="15" />
        </button>
        <button
          type="button"
          class="page-btn"
          title="最后一页"
          :disabled="page >= totalPages"
          @click="goToPage(totalPages)"
        >
          <ChevronsRight :size="15" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ui-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-top: none;
  font-size: 12px;
  color: var(--muted);
  box-sizing: border-box;
}

.pagination-info {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.pagination-info strong {
  color: var(--color-text);
  font-weight: 700;
}

.pagination-range {
  color: var(--muted);
}

.pagination-controls {
  display: inline-flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.pagination-size {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.pagination-size select {
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xs);
  background: var(--surface);
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text);
  cursor: pointer;
}

.pagination-buttons {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.page-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--color-text);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-base);
  user-select: none;
}

.page-btn:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: var(--surface-soft);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-color: var(--line);
}

.page-indicator {
  padding: 0 8px;
  font-size: 12px;
  white-space: nowrap;
  color: var(--muted);
}

.page-indicator strong {
  color: var(--color-accent);
  font-weight: 700;
}
</style>
