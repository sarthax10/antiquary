import { api } from "./client";

export const getCurrentUser = () => api.get("/api/auth/me").then((d) => d.user);
export const signup = (email, password) => api.post("/api/auth/signup", { email, password });
export const login = (email, password) => api.post("/api/auth/login", { email, password }).then((d) => d.user);
export const logout = () => api.post("/api/auth/logout");
export const changePassword = (currentPassword, newPassword) =>
  api.post("/api/auth/change-password", { current_password: currentPassword, new_password: newPassword });
