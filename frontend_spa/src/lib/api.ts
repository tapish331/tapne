import { getFrontendConfig } from "@frontend/lib/config";

export type JsonObject = Record<string, unknown>;

export type FrontendTrip = {
  id: number;
  title: string;
  summary?: string;
  description?: string;
  description_html?: string;
  destination?: string;
  banner_image_url?: string;
  host_username?: string;
  host_display_name?: string;
  host_avatar_url?: string;
  host_bio?: string;
  host_location?: string;
  traffic_score?: number;
  url?: string;
  starts_at?: string;
  ends_at?: string;
  booking_closes_at?: string;
  booking_closes_label?: string;
  date_label?: string;
  season_label?: string;
  duration_days?: number;
  duration_bucket?: string;
  duration_label?: string;
  trip_type?: string;
  trip_type_label?: string;
  budget_tier?: string;
  budget_label?: string;
  budget_range_label?: string;
  cost_label?: string;
  difficulty_level?: string;
  difficulty_label?: string;
  pace_level?: string;
  pace_label?: string;
  group_size_label?: string;
  total_seats?: number;
  minimum_seats?: number;
  spots_left_label?: string;
  currency?: string;
  total_trip_price?: string | number;
  price_per_person?: string | number;
  early_bird_price?: string | number;
  payment_terms?: string;
  includes_label?: string;
  highlights?: string[];
  itinerary_days?: Array<Record<string, unknown>>;
  included_items?: string[];
  not_included_items?: string[];
  things_to_carry?: string[];
  suitable_for?: string[];
  trip_vibe?: string[];
  general_policies?: string;
  code_of_conduct?: string;
  cancellation_policy?: string;
  faqs?: Array<Record<string, unknown>>;
};

export type FrontendBlog = {
  id?: number;
  slug: string;
  title: string;
  excerpt?: string;
  summary?: string;
  author_username?: string;
  author_display_name?: string;
  reads?: number;
  reviews_count?: number;
  url?: string;
  body?: string;
  cover_image_url?: string;
  published_label?: string;
};

export type FrontendProfile = {
  id?: number;
  username: string;
  bio?: string;
  followers_count?: number;
  trips_count?: number;
  url?: string;
  display_name?: string;
  location?: string;
  website?: string;
  email?: string;
};

export async function apiGet<T>(url: string): Promise<T> {
  return apiRequest<T>(url, { method: "GET" });
}

export async function apiPost<T>(url: string, payload?: JsonObject): Promise<T> {
  return apiRequest<T>(url, { method: "POST", payload });
}

export async function apiPatch<T>(url: string, payload?: JsonObject): Promise<T> {
  return apiRequest<T>(url, { method: "PATCH", payload });
}

export async function apiDelete<T>(url: string): Promise<T> {
  return apiRequest<T>(url, { method: "DELETE" });
}

export function apiUrl(key: string): string {
  const config = getFrontendConfig();
  const value = config.api[key];
  if (!value) {
    throw new Error(`Missing API route for ${key}.`);
  }
  return value;
}

async function apiRequest<T>(
  url: string,
  options: {
    method: string;
    payload?: JsonObject;
  },
): Promise<T> {
  const config = getFrontendConfig();
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (options.payload) {
    headers["Content-Type"] = "application/json";
  }
  if (config.csrf?.header_name && config.csrf?.token) {
    headers[config.csrf.header_name] = config.csrf.token;
  }

  const response = await fetch(url, {
    method: options.method,
    credentials: "same-origin",
    headers,
    body: options.payload ? JSON.stringify(options.payload) : undefined,
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? ((await response.json()) as T | JsonObject)
    : (({} as T));

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? String((payload as JsonObject).error ?? "Request failed.")
        : "Request failed.";
    throw new Error(message);
  }

  return payload as T;
}
