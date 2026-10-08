export interface ApiError {
  status: number
  message: string
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  })

  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') {
        message = data.detail
      } else if (Array.isArray(data?.detail)) {
        message = data.detail.map((item: { msg?: string }) => item.msg || '参数错误').join('；')
      }
    } catch {
      /* keep the generic message */
    }
    const error: ApiError = { status: response.status, message }
    throw error
  }

  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export function errorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as ApiError).message)
  }
  return '发生未知错误，请重试'
}
