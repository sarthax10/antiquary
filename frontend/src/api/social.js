import { api } from "./client";

export const listAccounts = () => api.get("/api/social/accounts").then((d) => d.accounts);
export const disconnectAccount = (id) => api.del(`/api/social/accounts/${id}`);

// These aren't fetch() calls — connecting is a full-page OAuth redirect, not an API
// request the SPA can await. Pages just navigate the browser here directly.
export const connectUrl = (platform) => `/api/social/${platform}/connect`;
