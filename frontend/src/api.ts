export async function api<T>(url: string, options?: RequestInit): Promise<T> {
 const response = await fetch(url, options);
 if (!response.ok) {
   const data = await response.json().catch(() => ({}));
   throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка сервера (${response.status})`);
 }
 return response.status === 204 ? undefined as T : response.json();
}
