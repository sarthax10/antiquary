import { api } from "./client";

export const listUsers = (status) =>
  api.get(`/api/admin/users${status ? `?status=${status}` : ""}`).then((d) => d.users);

export const setUserStatus = (userId, status) =>
  api.post(`/api/admin/users/${userId}/status`, { status }).then((d) => d.user);
