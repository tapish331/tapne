import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter, Outlet, Navigate } from "react-router-dom";
import { useRef, useEffect } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { DraftProvider } from "@/contexts/DraftContext";
import LoginModal from "@/components/LoginModal";
import ScrollToTop from "@/components/ScrollToTop";

// All user-facing pages come from the Lovable source (@/ = lovable/src/),
// with explicit production overrides wired through vite.production.config.ts.
import Index from "@/pages/Index";
import TripDetail from "@/pages/TripDetail";
import CreateTrip from "@/pages/CreateTrip";
import StoryDetail from "@/pages/StoryDetail";
import StoryCreate from "@/pages/StoryCreate";
import StoryEdit from "@/pages/StoryEdit";
import Profile from "@/pages/Profile";
import ProfileEdit from "@/pages/ProfileEdit";
import Bookmarks from "@/pages/Bookmarks";
import Messages from "@/pages/Messages";
import Search from "@/pages/Search";
import Notifications from "@/pages/Notifications";
import Settings from "@/pages/Settings";
import Dashboard from "@/pages/Dashboard";
import DashboardTrips from "@/pages/dashboard/DashboardTrips";
import DashboardStories from "@/pages/dashboard/DashboardStories";
import DashboardReviews from "@/pages/dashboard/DashboardReviews";
import DashboardSubscriptions from "@/pages/dashboard/DashboardSubscriptions";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

// Mirrors the GlobalLoginModal in lovable/src/App.tsx — required for the
// .js-guest-action / loginModalOpen flow to work in production.
const GlobalLoginModal = () => {
  const { loginModalOpen, setLoginModalOpen, pendingAuthAction } = useAuth();
  const pendingRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (pendingAuthAction !== null) {
      pendingRef.current = pendingAuthAction;
    }
  }, [pendingAuthAction]);

  return (
    <LoginModal
      open={loginModalOpen}
      onOpenChange={(open) => {
        setLoginModalOpen(open);
        if (!open) pendingRef.current = null;
      }}
      onSuccess={() => {
        const action = pendingRef.current;
        pendingRef.current = null;
        action?.();
      }}
    />
  );
};

// Root layout injects ScrollToTop, GlobalLoginModal, and DraftProvider into every route.
// DraftProvider MUST be inside the router — DraftContext calls useNavigate(),
// which throws if rendered outside a <Router> ancestor.
const RootLayout = () => (
  <DraftProvider>
    <ScrollToTop />
    <GlobalLoginModal />
    <Outlet />
  </DraftProvider>
);

// Route list mirrors the canonical route map in RULES.md §6. The only
// intentional deviation from lovable/src/App.tsx is the trip param name:
// `/trips/:id` keeps the active TripDetail override aligned with its
// `const { id } = useParams()` implementation.
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: "/", element: <Index /> },

      // Search and trips
      { path: "/search", element: <Search /> },
      { path: "/trips/new", element: <CreateTrip /> },
      { path: "/trips/:id/edit", element: <CreateTrip /> },
      { path: "/trips/:id", element: <TripDetail /> },

      // Stories
      { path: "/stories/new", element: <StoryCreate /> },
      { path: "/stories/:storyId/edit", element: <StoryEdit /> },
      { path: "/stories/:storyId", element: <StoryDetail /> },

      // Profile / Users
      { path: "/profile/edit", element: <ProfileEdit /> },
      { path: "/users/:profileId", element: <Profile /> },

      // Messaging & utility
      { path: "/messages", element: <Messages /> },
      { path: "/bookmarks", element: <Bookmarks /> },
      { path: "/404", element: <NotFound /> },
      { path: "/notifications", element: <Notifications /> },
      { path: "/settings", element: <Settings /> },

      // Dashboard (nested)
      {
        path: "/dashboard",
        element: <Dashboard />,
        children: [
          { index: true, element: <Navigate to="/dashboard/trips" replace /> },
          { path: "trips", element: <DashboardTrips /> },
          { path: "stories", element: <DashboardStories /> },
          { path: "reviews", element: <DashboardReviews /> },
          { path: "subscriptions", element: <DashboardSubscriptions /> },
        ],
      },

      { path: "*", element: <NotFound /> },
    ],
  },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <RouterProvider router={router} />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
