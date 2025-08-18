const API_BASE = import.meta.env.VITE_API_BASE || "/api";
async function parseProblem(res) {
  let detail = `${res.status} ${res.statusText}`
  try {
    const data = await res.json()
    if (data.detail) detail = data.detail
    else if (data.title) detail = data.title
  } catch (ex) {
    const err = new Error(ex.message);
    err.status = res.status;
    throw err;
  }
  return detail;  
}

export async function api(path, { method='GET', headers={}, body } = {}, token) {
  const finalHeaders = { ...headers }
  if (token) finalHeaders['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}${path}`, { method, headers: finalHeaders, body })
  if (!res.ok) await parseProblem(res)
  return res
}

export async function apiJSON(path, options={}, token) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const finalBody = options.body ? JSON.stringify(options.body) : undefined;
  const res = await api(path, { ...options, headers, body: finalBody }, token);

  if (res.ok) {
    return res.json()
  } else {
    const errText = await res.text()
    throw new Error(errText)
  }
}

export const API_BASE_URL = API_BASE
