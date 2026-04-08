import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter, Outlet } from "react-router-dom";
import { useRef, useEffect } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { DraftProvider } from "@/contexts/DraftContext";
import { useAuth } from "@/contexts/AuthContext";
import LoginModal from "@/components/LoginModal";
import ScrollToTop from "@/components/ScrollToTop";

// All user-facing pages come from the Lovable source (@/ = lovable/src/).
// Never import page components from @frontend/pages except UnderConstructionPage.
import Index from "@/pages/Index";
import BrowseTrips from "@/pages/BrowseTrips";
import TripPreview from "@/pages/TripPreview";
import TripDetail from "@/pages/TripDetail";
import CreateTrip from "@/pages/CreateTrip";
import MyTrips from "@/pages/MyTrips";
import Experiences from "@/pages/Experiences";
import ExperienceCreate from "@/pages/ExperienceCreate";
import ExperienceEdit from "@/pages/ExperienceEdit";
import ExperienceDetail from "@/pages/ExperienceDetail";
import TravelHosts from "@/pages/TravelHosts";
import Bookmarks from "@/pages/Bookmarks";
import Inbox from "@/pages/Inbox";
import ManageTrip from "@/pages/ManageTrip";
import Login from "@/pages/Login";
import SignUp from "@/pages/SignUp";
import Profile from "@/pages/Profile";
import UnderConstructionPage from "@frontend/pages/UnderConstructionPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

// Mirrors the GlobalLoginModal in lovable/src/App.tsx — required for the
// .js-guest-action / loginModalOpen flow to work in production.
//
// pendingAuthAction is captured in a ref so the callback is reliably called
// even though React batches the state update (setLoginModalOpen → setPendingAuthAction)
// before onSuccess fires.
const GlobalLoginModal = () => {
  const { loginModalOpen, setLoginModalOpen, pendingAuthAction } = useAuth();
  const pendingRef = useRef<(() => void) | null>(null);

  // Keep ref in sync whenever a new pending action is registered
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

// Root layout injects ScrollToTop and GlobalLoginModal into every route.
// With createBrowserRouter these can't be placed inside BrowserRouter directly,
// so they live in a layout route that wraps all children via <Outlet />.
const RootLayout = () => (
  <>
    <ScrollToTop />
    <GlobalLoginModal />
    <Outlet />
  </>
);

// Route list must match lovable/src/App.tsx exactly.
// The only permitted deviation: * catch-all → UnderConstructionPage (not NotFound).
// /blogs intentionally maps to Experiences — this mirrors lovable/src/App.tsx.
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: "/",                   element: <Index /> },
      { path: "/trips",              element: <BrowseTrips /> },
      { path: "/trips/preview",      element: <TripPreview /> },
      { path: "/trips/:id",          element: <TripDetail /> },
      { path: "/create-trip",        element: <CreateTrip /> },
      { path: "/my-trips",           element: <MyTrips /> },
      { path: "/experiences",        element: <Experiences /> },
      { path: "/experiences/create", element: <ExperienceCreate /> },
      { path: "/experiences/edit",   element: <ExperienceEdit /> },
      { path: "/experiences/:slug",  element: <ExperienceDetail /> },
      { path: "/blogs",              element: <Experiences /> },
      { path: "/travel-hosts",       element: <TravelHosts /> },
      { path: "/bookmarks",          element: <Bookmarks /> },
      { path: "/inbox",              element: <Inbox /> },
      { path: "/manage-trip/:id",    element: <ManageTrip /> },
      { path: "/login",              element: <Login /> },
      { path: "/signup",             element: <SignUp /> },
      { path: "/profile",            element: <Profile /> },
      { path: "/profile/:userId",    element: <Profile /> },
      { path: "*",                   element: <UnderConstructionPage /> },
    ],
  },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DraftProvider>
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <RouterProvider router={router} />
          </TooltipProvider>
        </DraftProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
