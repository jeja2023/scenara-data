<script setup lang="ts">
import type { Component } from "vue";

export interface TabItem {
  id: string;
  label: string;
  icon?: Component;
  badge?: string | number;
}

const props = defineProps<{
  tabs: TabItem[];
  modelValue: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
}>();

function selectTab(id: string): void {
  emit("update:modelValue", id);
}
</script>

<template>
  <div class="ui-tabs" role="tablist">
    <button
      v-for="tab in props.tabs"
      :key="tab.id"
      type="button"
      class="ui-tab-item"
      :class="{ active: props.modelValue === tab.id }"
      role="tab"
      :aria-selected="props.modelValue === tab.id"
      @click="selectTab(tab.id)"
    >
      <component :is="tab.icon" v-if="tab.icon" :size="16" class="tab-icon" />
      <span class="tab-label">{{ tab.label }}</span>
      <span v-if="tab.badge !== undefined && tab.badge !== null" class="tab-badge">
        {{ tab.badge }}
      </span>
    </button>
  </div>
</template>

<style scoped>
.ui-tabs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  overflow-x: auto;
  max-width: 100%;
}

.ui-tab-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  height: 34px;
  padding: 0 16px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: var(--transition-base);
  user-select: none;
}

.ui-tab-item:hover {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.6);
}

.ui-tab-item.active {
  background: var(--surface);
  color: var(--color-accent);
  border-color: var(--line);
  box-shadow: var(--shadow-xs);
}

.tab-icon {
  flex-shrink: 0;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  border-radius: 9px;
  background: rgba(47, 107, 138, 0.1);
  color: var(--color-accent);
}

.ui-tab-item.active .tab-badge {
  background: var(--color-accent);
  color: #ffffff;
}
</style>
