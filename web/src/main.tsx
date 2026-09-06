import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WebStorageStateStore } from "oidc-client-ts";
import React from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider, type AuthProviderProps } from "react-oidc-context";

import App from "./App";
import { CLIENT_ID, OIDC_AUTHORITY } from "./config";
import "./index.css";

const oidc: AuthProviderProps = {
  authority: OIDC_AUTHORITY,
  client_id: CLIENT_ID,
  redirect_uri: `${location.origin}/`,
  post_logout_redirect_uri: `${location.origin}/`,
  // Authorization code + PKCE. There is no client secret, because anything
  // shipped to a browser is public.
  response_type: "code",
  scope: "openid profile email",
  // ponytail: sessionStorage, so a refresh keeps the session. It is readable by
  // any XSS on this origin. The upgrade path is a BFF holding tokens in
  // httpOnly cookies, which is a whole extra service.
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  onSigninCallback: () => history.replaceState({}, "", location.pathname),
};

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider {...oidc}>
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>
    </AuthProvider>
  </React.StrictMode>,
);
