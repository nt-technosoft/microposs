<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  width?: string
  height?: string
  rounded?: boolean
  circle?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  width: '100%',
  height: '1rem',
  rounded: false,
  circle: false,
})

const style = computed(() => ({
  width: props.circle ? props.height : props.width,
  height: props.height,
}))
</script>

<template>
  <span
    class="skeleton"
    :class="{
      'skeleton--rounded': rounded,
      'skeleton--circle': circle,
    }"
    :style="style"
    aria-hidden="true"
  />
</template>

<style scoped>
.skeleton {
  display: block;
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 25%,
    var(--color-bg-sunken) 50%,
    var(--color-bg-secondary) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
  border-radius: var(--radius-sm);
}

.skeleton--rounded {
  border-radius: var(--radius-md);
}

.skeleton--circle {
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
</style>
