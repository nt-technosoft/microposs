<script setup lang="ts">
import BaseSkeletonLoader from '@/components/base/BaseSkeletonLoader.vue'
</script>

<template>
  <div class="skeleton-card" aria-hidden="true">
    <!-- Image placeholder (4/3 aspect ratio) -->
    <div class="skeleton-image">
      <span class="skeleton-image-fill" />
    </div>

    <!-- Content area -->
    <div class="skeleton-content">
      <!-- Product name — two lines -->
      <div class="skeleton-lines">
        <BaseSkeletonLoader width="85%" height="0.875rem" />
        <BaseSkeletonLoader width="60%" height="0.875rem" />
      </div>

      <!-- Price line -->
      <BaseSkeletonLoader width="50%" height="1.125rem" :rounded="true" />

      <!-- Action button -->
      <BaseSkeletonLoader width="100%" height="40px" :rounded="true" />
    </div>
  </div>
</template>

<style scoped>
.skeleton-card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

/* 4:3 aspect ratio image placeholder */
.skeleton-image {
  position: relative;
  width: 100%;
  padding-top: 75%;
  overflow: hidden;
}

.skeleton-image-fill {
  position: absolute;
  inset: 0;
  display: block;
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 25%,
    var(--color-bg-sunken) 50%,
    var(--color-bg-secondary) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
}

@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton-content {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
</style>
