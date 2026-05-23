// HTTP client. The ONLY file in the frontend that calls fetch.
// See ARCHITECTURE.md ("Hard rules").

export async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function apiPut(path, body) {
  const response = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function apiDelete(path) {
  const response = await fetch(path, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  if (response.status === 204) {
    return null;
  }
  return response.json().catch(() => null);
}
