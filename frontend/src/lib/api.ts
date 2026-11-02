import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "/api";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("access_token");
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error),
);

let isRefreshing = false;
let refreshPromise: Promise<string> | null = null;

// Response interceptor for token refresh / auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      !originalRequest?._retry &&
      !originalRequest?.url?.includes("/auth/")
    ) {
      originalRequest._retry = true;

      try {
        if (!isRefreshing) {
          isRefreshing = true;

          refreshPromise = new Promise(async (resolve, reject) => {
            try {
              const refreshToken = localStorage.getItem("refresh_token");
              if (!refreshToken) throw new Error("No refresh token");

              const response = await axios.post(`${API_URL}/auth/refresh`, {
                refresh_token: refreshToken,
              });

              const { access_token, refresh_token: new_refresh_token } = response.data;
              localStorage.setItem("access_token", access_token);
              localStorage.setItem("refresh_token", new_refresh_token);

              resolve(access_token);
            } catch (refreshError) {
              localStorage.removeItem("access_token");
              localStorage.removeItem("refresh_token");
              const currentPath = typeof window !== "undefined" ? window.location.pathname : "";
              const isPublicPage =
                currentPath === "/" ||
                currentPath.startsWith("/login") ||
                currentPath.startsWith("/register") ||
                currentPath.startsWith("/forgot-password") ||
                currentPath.startsWith("/reset-password") ||
                currentPath.startsWith("/help");

              if (typeof window !== "undefined" && !isPublicPage) {
                window.location.replace("/login");
              }
              reject(refreshError);
            } finally {
              isRefreshing = false;
              refreshPromise = null;
            }
          });
        }

        if (refreshPromise) {
          const token = await refreshPromise;
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);
