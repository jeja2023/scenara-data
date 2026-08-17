import {
  clearConnectionToken,
  saveConnection,
  type ConnectionSettings,
} from "./api";

const AUTH_STORAGE_KEY = "scenara.data.console.auth.v1";
const AUTH_EXPIRES_KEY = "scenara.data.console.auth.expires.v1";

export function isSignedIn(): boolean {
  const expiresAt =
    sessionStorage.getItem(AUTH_EXPIRES_KEY) ??
    localStorage.getItem(AUTH_EXPIRES_KEY);
  if (expiresAt) {
    const value = Number(expiresAt);
    if (Number.isFinite(value) && Date.now() / 1000 >= value) {
      signOut();
      return false;
    }
  }
  return (
    sessionStorage.getItem(AUTH_STORAGE_KEY) === "1" ||
    localStorage.getItem(AUTH_STORAGE_KEY) === "1"
  );
}

export function completeSignIn(
  connection: ConnectionSettings,
  remember: boolean,
  expiresAt?: number,
): void {
  saveConnection(connection, { persistAuth: remember });
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  localStorage.removeItem(AUTH_STORAGE_KEY);
  sessionStorage.removeItem(AUTH_EXPIRES_KEY);
  localStorage.removeItem(AUTH_EXPIRES_KEY);
  const storage = remember ? localStorage : sessionStorage;
  storage.setItem(AUTH_STORAGE_KEY, "1");
  if (expiresAt && Number.isFinite(expiresAt)) {
    storage.setItem(AUTH_EXPIRES_KEY, String(expiresAt));
  }
}

export function signOut(): void {
  sessionStorage.removeItem(AUTH_STORAGE_KEY);
  localStorage.removeItem(AUTH_STORAGE_KEY);
  sessionStorage.removeItem(AUTH_EXPIRES_KEY);
  localStorage.removeItem(AUTH_EXPIRES_KEY);
  clearConnectionToken();
}
