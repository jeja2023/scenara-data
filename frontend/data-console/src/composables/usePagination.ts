import { computed, ref, type Ref } from "vue";

export function usePagination<T>(itemsRef: Ref<T[]>, initialPageSize: number = 10) {
  const page = ref(1);
  const pageSize = ref(initialPageSize);

  const total = computed(() => itemsRef.value.length);
  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));

  const paginatedItems = computed(() => {
    const start = (page.value - 1) * pageSize.value;
    return itemsRef.value.slice(start, start + pageSize.value);
  });

  function resetPage(): void {
    page.value = 1;
  }

  return {
    page,
    pageSize,
    total,
    totalPages,
    paginatedItems,
    resetPage,
  };
}
