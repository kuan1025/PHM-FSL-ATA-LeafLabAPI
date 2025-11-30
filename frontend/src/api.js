import { getIdToken } from './auth';

export const API_BASE = import.meta.env.VITE_API_BASE || '/api';
export const API_VERSION = import.meta.env.VITE_API_VERSION || 'v1';
export const PRESIGN_ENDPOINT = import.meta.env.VITE_PRESIGN_ENDPOINT || '';


export function buildUrl(path) {
  return `${API_BASE}${path}`;
}

async function parseProblem(res) {
  const statusLine = `${res.status} ${res.statusText}`;
  try {
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      const data = await res.clone().json();
      if (data?.detail) return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      if (data?.title) return data.title;
      return JSON.stringify(data);
    } else {
      const txt = await res.clone().text();
      return txt || statusLine;
    }
  } catch {
    return statusLine;
  }
}

function bearerHeader(overrideToken) {
  const t = overrideToken ?? getIdToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}


export async function api(path, { method = 'GET', headers = {}, body } = {}, tokenOverride) {
  const finalHeaders = { ...headers, ...bearerHeader(tokenOverride) };
  const res = await fetch(buildUrl(path), { method, headers: finalHeaders, body });
  if (!res.ok) {
    throw new Error(await parseProblem(res));
  }
  return res;
}


export async function apiJSON(path, options = {}, tokenOverride) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const body = options.body !== undefined ? JSON.stringify(options.body) : undefined;
  const res = await api(path, { ...options, headers, body }, tokenOverride);
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export async function apiForm(path, form, options = {}, tokenOverride) {
  const headers = { 'Content-Type': 'application/x-www-form-urlencoded', ...(options.headers || {}) };
  const body = form instanceof URLSearchParams ? form : new URLSearchParams(form);
  const res = await api(path, { ...options, method: options.method || 'POST', headers, body }, tokenOverride);
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}


export const API_BASE_URL = API_BASE;
