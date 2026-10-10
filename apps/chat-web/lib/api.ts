import axios from "axios";

/** For Python backend API calls */
export const api = axios.create({
  baseURL: process.env.CHAT_API_BASE_URL,
  headers: { "x-internal-key": process.env.CHAT_API_INTERNAL_KEY || "" },
});

/** For internal Next.js API routes (relative paths) */
export const localApi = axios.create();

export function handleApiError(error: unknown) {
  if (axios.isAxiosError(error) && error.response) {
    return {
      data: error.response.data,
      status: error.response.status,
    };
  }
  return {
    data: { error: "Upstream API unreachable" },
    status: 502 as const,
  };
}
