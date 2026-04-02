export type FrontendUser = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  bio: string;
  location: string;
  website: string;
  profile_url: string;
  public_profile_url: string;
};

export type FrontendConfig = {
  api: Record<string, string>;
  routes: Record<string, string>;
  auth: Record<string, string>;
  csrf: {
    cookie_name?: string;
    header_name?: string;
    token?: string;
  };
  session?: {
    authenticated?: boolean;
    user?: FrontendUser | null;
  };
};

export function getFrontendConfig(): FrontendConfig {
  const config = window.__TAPNE_FRONTEND_CONFIG__;
  if (!config || typeof config !== "object") {
    throw new Error("Missing frontend runtime config.");
  }
  return config as FrontendConfig;
}

export function getInitialUser(): FrontendUser | null {
  const config = getFrontendConfig();
  return config.session?.user ?? null;
}
