import { api } from "./client";

export const listPublications = (storyId) => api.get(`/api/publish/${storyId}`).then((d) => d.publications);
export const startPublish = (storyId, platform) => api.post(`/api/publish/${storyId}`, { platform });
