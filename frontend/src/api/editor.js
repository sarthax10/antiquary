import { api } from "./client";

export const getTimeline = (id) => api.get(`/api/stories/${id}/editor`);
export const updateCaption = (id, capId, text) =>
  api.patch(`/api/stories/${id}/editor/captions/${capId}`, { text }).then((d) => d.timeline);
export const startRender = (id) => api.post(`/api/stories/${id}/editor/render`);
export const getRenderStatus = (id) => api.get(`/api/stories/${id}/editor/render/status`);
