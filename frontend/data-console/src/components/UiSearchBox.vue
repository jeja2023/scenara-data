<script setup lang="ts">
import { Search, X } from "@lucide/vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    placeholder?: string;
    width?: string;
  }>(),
  {
    placeholder: "输入关键词搜索...",
    width: "280px",
  },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "search", value: string): void;
}>();

function onInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  emit("update:modelValue", value);
}

function clear(): void {
  emit("update:modelValue", "");
  emit("search", "");
}

function onEnter(): void {
  emit("search", props.modelValue);
}
</script>

<template>
  <div class="ui-search-box" :style="{ width: props.width }">
    <Search :size="15" class="search-icon" />
    <input
      :value="modelValue"
      type="text"
      class="search-input"
      :placeholder="placeholder"
      @input="onInput"
      @keydown.enter="onEnter"
    />
    <button
      v-if="modelValue"
      type="button"
      class="search-clear"
      title="清空"
      @click="clear"
    >
      <X :size="14" />
    </button>
  </div>
</template>

<style scoped>
.ui-search-box {
  position: relative;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
}

.search-icon {
  position: absolute;
  left: 10px;
  color: var(--muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 32px;
  min-height: 32px;
  padding: 0 28px 0 32px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--color-text);
  font-size: 12px;
  transition: var(--transition-base);
}

.search-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px rgba(47, 107, 138, 0.12);
  outline: none;
}

.search-clear {
  position: absolute;
  right: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  border-radius: 50%;
}

.search-clear:hover {
  color: var(--color-text);
  background: var(--surface-soft);
}
</style>
