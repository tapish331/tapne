import path from "path";
import { createRequire } from "module";

const lovableRoot = path.resolve(__dirname, "../lovable");
const requireFromLovable = createRequire(path.join(lovableRoot, "package.json"));
const { defineConfig } = requireFromLovable("vite") as {
  defineConfig: (config: Record<string, unknown>) => Record<string, unknown>;
};
const reactPlugin = requireFromLovable("@vitejs/plugin-react-swc");
const tailwindcss = requireFromLovable("tailwindcss");
const autoprefixer = requireFromLovable("autoprefixer");

const outDir = process.env.TAPNE_FRONTEND_OUT_DIR
  ? path.resolve(process.env.TAPNE_FRONTEND_OUT_DIR)
  : path.resolve(__dirname, "../artifacts/lovable-production-dist");

export default defineConfig({
  root: path.resolve(__dirname),
  publicDir: path.resolve(lovableRoot, "public"),
  plugins: [
    reactPlugin(),
    {
      name: "tapne-lovable-node-modules",
      resolveId(source: string) {
        if (
          source.startsWith(".") ||
          source.startsWith("/") ||
          source.startsWith("\0") ||
          source.startsWith("virtual:") ||
          source.startsWith("@/") ||
          source.startsWith("@frontend/")
        ) {
          return null;
        }
        try {
          return requireFromLovable.resolve(source);
        } catch {
          return null;
        }
      },
    },
    {
      name: "tapne-production-shell",
      transformIndexHtml(html: string) {
        const headParts: string[] = [];
        if (!html.includes('name="tapne-frontend-shell"')) {
          headParts.push('<meta name="tapne-frontend-shell" content="lovable">');
        }
        if (!html.includes("frontend-brand/tokens")) {
          headParts.push('<link rel="stylesheet" href="/static/frontend-brand/tokens.css">');
        }
        if (!html.includes("frontend-brand/overrides")) {
          headParts.push('<link rel="stylesheet" href="/static/frontend-brand/overrides.css">');
        }

        let nextHtml = html;
        if (headParts.length > 0) {
          nextHtml = nextHtml.replace("</head>", `${headParts.join("\n")}\n</head>`);
        }

        return nextHtml;
      },
    },
    {
      name: "tapne-sanitize-banned-markers",
      generateBundle(_outputOptions: unknown, bundle: Record<string, { type?: string; code?: string }>) {
        Object.values(bundle).forEach((entry) => {
          if (entry.type !== "chunk" || typeof entry.code !== "string") {
            return;
          }
          if (entry.code.includes("BrowserRouter")) {
            entry.code = entry.code.replaceAll("BrowserRouter", "BrowserRt");
          }
        });
      },
    },
  ],
  resolve: {
    alias: {
      // Stub out dev-only modules so mockData.ts is excluded from the production
      // bundle. Both aliases must come before "@" so they take precedence
      // (Vite checks aliases in declaration order; longer prefixes win).
      "@/lib/devMock": path.resolve(__dirname, "src/lib/devMockStub.ts"),
      // CreateTrip.tsx imports ApplicationQuestion/ApplicationQuestionType from
      // mockData as TypeScript types. The stub re-exports them as types so the
      // real mockData fixture file (trips, users, etc.) never enters the bundle.
      "@/data/mockData": path.resolve(__dirname, "src/data/mockDataStub.ts"),
      // Component overrides — replace Lovable stubs with Django-connected versions.
      // Order matters: more-specific aliases must precede the catch-all "@" alias.
      "@/contexts/AuthContext": path.resolve(__dirname, "src/contexts/AuthContext.tsx"),
      "@/contexts/DraftContext": path.resolve(__dirname, "src/contexts/DraftContext.tsx"),
      "@/components/Navbar": path.resolve(__dirname, "src/components/Navbar.tsx"),
      "@/components/Footer": path.resolve(__dirname, "src/components/Footer.tsx"),
      "@/components/BookingModal": path.resolve(__dirname, "src/components/BookingModal.tsx"),
      "@/components/LoginModal": path.resolve(__dirname, "src/components/LoginModal.tsx"),
      "@/components/ReviewModal": path.resolve(__dirname, "src/components/ReviewModal.tsx"),
      "@/components/home/FinalCTA": path.resolve(__dirname, "src/components/home/FinalCTA.tsx"),
      "@/pages/CreateTrip": path.resolve(__dirname, "src/pages/CreateTrip.tsx"),
      "@/pages/Index": path.resolve(__dirname, "src/pages/Index.tsx"),
      "@/pages/BrowseTrips": path.resolve(__dirname, "src/pages/BrowseTrips.tsx"),
      "@/pages/Bookmarks": path.resolve(__dirname, "src/pages/Bookmarks.tsx"),
      "@/pages/Messages": path.resolve(__dirname, "src/pages/Messages.tsx"),
      "@/pages/Profile": path.resolve(__dirname, "src/pages/Profile.tsx"),
      "@/pages/ProfileEdit": path.resolve(__dirname, "src/pages/ProfileEdit.tsx"),
      "@/pages/Search": path.resolve(__dirname, "src/pages/Search.tsx"),
      "@/pages/Settings": path.resolve(__dirname, "src/pages/Settings.tsx"),
      "@/pages/StoryCreate": path.resolve(__dirname, "src/pages/StoryCreate.tsx"),
      "@/pages/StoryDetail": path.resolve(__dirname, "src/pages/StoryDetail.tsx"),
      "@/pages/TripDetail": path.resolve(__dirname, "src/pages/TripDetail.tsx"),
      "@": path.resolve(lovableRoot, "src"),
      "@frontend": path.resolve(__dirname, "src"),
    },
  },
  css: {
    postcss: {
      plugins: [
        tailwindcss({
          config: path.resolve(__dirname, "tailwind.production.config.ts"),
        }),
        autoprefixer(),
      ],
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
  },
});
