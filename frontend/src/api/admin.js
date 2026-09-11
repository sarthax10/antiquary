import { api } from "./client";

export const listUsers = (status) =>
  api.get(`/api/admin/users${status ? `?status=${status}` : ""}`).then((d) => d.users);

export const setUserStatus = (userId, status) =>
  api.post(`/api/admin/users/${userId}/status`, { status }).then((d) => d.user);

export const setUserRole = (userId, role) =>
  api.post(`/api/admin/users/${userId}/role`, { role }).then((d) => d.user);

export const resetPassword = (userId, password) =>
  api.post(`/api/admin/users/${userId}/reset-password`, { password }).then((d) => d.user);
