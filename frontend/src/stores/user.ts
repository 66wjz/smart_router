import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getToken, removeToken, setToken } from '@/utils/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref(getToken())

  function login(newToken: string) {
    token.value = newToken
    setToken(newToken)
  }

  function logout() {
    token.value = ''
    removeToken()
  }

  return { token, login, logout }
})
