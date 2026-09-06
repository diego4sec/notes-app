import { useCallback } from "react";
import { useAuth } from "react-oidc-context";

import { API_BASE } from "./config";

export type Note = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export function useApi() {
  const auth = useAuth();
  const token = auth.user?.access_token;

  return useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const res = await fetch(`${API_BASE}/api${path}`, {
        ...init,
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${token}`,
          ...init.headers,
        },
      });

      // An expired access token is the normal case, not an error case.
      if (res.status === 401) {
        void auth.signinRedirect();
        throw new Error("session expired");
      }
      if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
      return res.status === 204 ? (null as T) : (res.json() as Promise<T>);
    },
    [token, auth],
  );
}
