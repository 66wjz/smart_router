<template>
  <div class="form-group">
    <label>
      {{ label }}<span v-if="required" class="req">*</span>
    </label>
    <slot />
    <div v-if="error" class="field-error">{{ error }}</div>
    <div v-else-if="hint" class="field-hint">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  required?: boolean
  error?: string
  hint?: string
}>()
</script>

<style scoped>
.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.form-group label .req {
  color: var(--accent-red);
  margin-left: 2px;
}
.field-error {
  font-size: 12px;
  color: var(--accent-red);
  margin-top: 4px;
}
.field-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}
</style>
