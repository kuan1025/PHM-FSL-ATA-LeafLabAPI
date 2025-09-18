const KEY = 'leaflab.jwt'


export function setTokens(t) {
  localStorage.setItem(KEY, JSON.stringify(t || {}));
}

export function getTokens() {
  try { return JSON.parse(localStorage.getItem(KEY) || '{}'); }
  catch { return {}; }
}

export function getIdToken() {
  return getTokens().id_token || null;
}

export function clearTokens() {
  localStorage.removeItem(KEY);
}

export function getAccessToken() {
  return getTokens().access_token || null;
}

export function isAuthed() {
  return !!getAccessToken();
}