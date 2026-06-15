import axios from 'axios'

/**
 * Extract a human-readable error message from an unknown thrown value.
 *
 * Handles Axios errors (including backend `detail` field, timeouts and
 * network-unreachable cases) as well as generic Error / string fallbacks.
 */
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      return detail
    }
    if (error.code === 'ECONNABORTED') {
      return '请求超时，请确认后端服务是否正常运行。'
    }
    if (!error.response) {
      return '无法连接 Paris Agent 后端，请确认 8000 端口已启动。'
    }
    return `请求失败 (${error.response.status})，请稍后重试。`
  }
  if (error instanceof Error) {
    return error.message
  }
  return '请求处理失败，请稍后重试。'
}
