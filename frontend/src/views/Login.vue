<template>
  <div class="login-page">
    <BaseCard class="login-card">
      <div class="login-logo">
        <div class="logo-icon">
          <BaseIcon name="cpu" :size="20" color="#fff" />
        </div>
        <span>Smart Router</span>
      </div>
      <h2>欢迎使用</h2>
      <p class="subtitle">AI 模型智能路由代理 · v5</p>

      <BaseFormGroup label="用户名" :error="formErrors.username">
        <BaseInput v-model="form.username" placeholder="请输入用户名" @keyup.enter="handleLogin" />
      </BaseFormGroup>

      <BaseFormGroup label="密码" :error="formErrors.password">
        <div class="password-wrapper">
          <BaseInput
            v-model="form.password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
          <BaseButton variant="icon" type="button" class="toggle-pw" @click="showPassword = !showPassword">
            <BaseIcon v-if="!showPassword" name="eye" :size="14" />
            <BaseIcon v-else name="eye-off" :size="14" />
          </BaseButton>
        </div>
      </BaseFormGroup>

      <BaseButton
        variant="primary"
        block
        class="login-btn"
        :disabled="loading"
        @click="handleLogin"
      >
        {{ loading ? '登录中...' : '登 录' }}
      </BaseButton>

      <div class="login-footer">
        <div class="footer-hints">
          <span>默认账号 admin</span>
        </div>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseFormGroup from '@/components/base/BaseFormGroup.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseIcon from '@/components/base/BaseIcon.vue'
import { login } from '@/api/common'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const showPassword = ref(false)

const form = reactive({ username: '', password: '' })
const formErrors = reactive({ username: '', password: '' })

async function handleLogin() {
  formErrors.username = form.username.trim() ? '' : '请输入用户名'
  formErrors.password = form.password ? '' : '请输入密码'
  if (formErrors.username || formErrors.password) return

  loading.value = true
  try {
    const res: any = await login(form)
    userStore.login(res.token)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch {
    // request.ts 已统一提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: var(--bg-deep);
}

.login-page::before {
  content: '';
  position: absolute;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent-blue) 6%, transparent) 0%, transparent 70%);
  top: -200px;
  right: -100px;
  pointer-events: none;
}

.login-page::after {
  content: '';
  position: absolute;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.04) 0%, transparent 70%);
  bottom: -200px;
  left: -100px;
  pointer-events: none;
}

.login-card {
  width: 380px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  padding: 40px;
  box-shadow: var(--shadow-lg), var(--shadow-glow);
  position: relative;
  z-index: var(--z-base);
  animation: slideUp var(--duration-slow) var(--ease-out);
}

.login-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 32px;
}

.login-logo .logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-blue-hover));
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px color-mix(in srgb, var(--accent-blue) 20%, transparent);
}

.login-logo span {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.login-card h2 {
  font-size: 18px;
  font-weight: 600;
  text-align: center;
  margin-bottom: 6px;
  color: var(--text-primary);
}

.login-card .subtitle {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
  margin-bottom: 28px;
}

.password-wrapper {
  position: relative;
}

.password-wrapper :deep(.base-input) {
  padding-right: 40px;
}

.toggle-pw {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color var(--duration-fast);
}

.toggle-pw:hover {
  color: var(--text-secondary);
}

.login-btn {
  margin-top: 8px;
}

.login-footer {
  margin-top: 24px;
}

.footer-hints {
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(16px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
