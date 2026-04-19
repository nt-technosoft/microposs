<template>
  <div class="overlay">
    <div class="spinner" />
    <p>Loading…</p>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  display: grid;
  place-content: center;
  gap: var(--space-4);
  background: rgba(20, 33, 61, 0.18);
  color: var(--color-text-primary);
}

.spinner {
  width: 3rem;
  height: 3rem;
  border: 4px solid rgba(47, 111, 237, 0.2);
  border-top-color: var(--color-accent);
  border-radius: 999px;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
