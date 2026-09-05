<script setup lang="ts">
import { computed } from "vue";
import { useTooltip } from "../composables/useTooltip";

const { tooltipState } = useTooltip();

const style = computed(() => {
  if (tooltipState.value.placement === "bottom") {
    return {
      left: `${tooltipState.value.x}px`,
      top: `${tooltipState.value.y}px`,
      transform: "translate(-50%, 0)",
    };
  }
  return {
    left: `${tooltipState.value.x}px`,
    top: `${tooltipState.value.y}px`,
    transform: "translate(-50%, -100%)",
  };
});
</script>

<template>
  <Teleport to="body">
    <Transition name="tooltip-fade">
      <div
        v-if="tooltipState.visible && tooltipState.text"
        class="custom-tooltip"
        :class="tooltipState.placement"
        :style="style"
        role="tooltip"
      >
        <span class="custom-tooltip-text">{{ tooltipState.text }}</span>
        <span class="custom-tooltip-arrow"></span>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.custom-tooltip {
  position: fixed;
  z-index: 99999;
  pointer-events: none;
  max-width: 420px;
  min-width: 48px;
  padding: 6px 12px;
  background: #141e24;
  color: #f3f7fa;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.45;
  border-radius: 6px;
  box-shadow: 0 6px 20px rgba(10, 18, 23, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.12);
  word-break: break-all;
  white-space: normal;
  text-align: left;
}

.custom-tooltip-arrow {
  position: absolute;
  left: 50%;
  width: 8px;
  height: 8px;
  background: #141e24;
  transform: translateX(-50%) rotate(45deg);
}

.custom-tooltip.top .custom-tooltip-arrow {
  bottom: -4px;
  border-right: 1px solid rgba(255, 255, 255, 0.12);
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.custom-tooltip.bottom .custom-tooltip-arrow {
  top: -4px;
  border-left: 1px solid rgba(255, 255, 255, 0.12);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}

.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 120ms ease, transform 120ms ease;
}

.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, -95%) scale(0.96);
}

.custom-tooltip.bottom.tooltip-fade-enter-from,
.custom-tooltip.bottom.tooltip-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, 5%) scale(0.96);
}
</style>
