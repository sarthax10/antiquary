import { api } from "./client";

export const listStories = (status) => api.get(`/api/stories?status=${status}`).then((d) => d.stories);
export const recentStories = (limit = 8) => api.get(`/api/stories?recent=${limit}`).then((d) => d.stories);
export const getStory = (id) => api.get(`/api/stories/${id}`).then((d) => d.story);
export const decideStory = (id, action) => api.post(`/api/stories/${id}/decide`, { action }).then((d) => d.story);
export const restoreStory = (id) => api.post(`/api/stories/${id}/restore`).then((d) => d.story);

export const startGeneration = (topic) => api.post("/api/generate", { topic });
export const cancelGeneration = () => api.post("/api/generate/cancel");
export const generationStatus = () => api.get("/api/generate/status");

export const videoUrl = (id) => `/api/stories/${id}/video`;
