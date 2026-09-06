// Behind the ingress, web + api + keycloak share one host, so everything is
// derivable from the current origin and the production image needs no per-env
// build. The env vars exist only for the compose/dev setup, where Keycloak
// sits on its own port.
export const OIDC_AUTHORITY =
  import.meta.env.VITE_OIDC_AUTHORITY ?? `${location.origin}/auth/realms/notes`;

export const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export const CLIENT_ID = "notes-web";
