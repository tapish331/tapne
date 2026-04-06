import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { DraftProvider } from "@/contexts/DraftContext";
import { useAuth } from "@/contexts/AuthContext";
import LoginModal from "@/components/LoginModal";
import ScrollToTop from "@/components/ScrollToTop";
import { Outlet } from "react-router-dom";

// All user-facing pages come from the Lovable source (@/ = lovable/src/).
// Never import page components from @frontend/pages except UnderConstructionPage.
import Index from "@/pages/Index";
import BrowseTrips from "@/pages/BrowseTrips";
import TripDetail from "@/pages/TripDetail";
import CreateTrip from "@/pages/CreateTrip";
import MyTrips from "@/pages/MyTrips";
import Experiences from "@/pages/Experiences";
import ExperienceCreate from "@/pages/ExperienceCreate";
import ExperienceEdit from "@/pages/ExperienceEdit";
import ExperienceDetail from "@/pages/ExperienceDetail";
import ManageTrip from "@/pages/ManageTrip";
import TripPreview from "@/pages/TripPreview";
import TravelHosts from "@/pages/TravelHosts";
import Bookmarks from "@/pages/Bookmarks";
import Inbox from "@/pages/Inbox";
import Login from "@/pages/Login";
import SignUp from "@/pages/SignUp";
import Profile from "@/pages/Profile";
import UnderConstructionPage from "@frontend/pages/UnderConstructionPage";

const queryClient = new QueryClient();

// Mirror of lovable/src/App.tsx GlobalLoginModal.
// Must be rendered inside <AuthProvider> — positioned as a sibling of
// <RouterProvider> so it doesn't need the router context.
const GlobalLoginModal = () => {
  const { loginModalOpen, setLoginModalOpen, pendingAuthAction } = useAuth();
  return (
    <LoginModal
      open={loginModalOpen}
      onOpenChange={setLoginModalOpen}
      onSuccess={() => {
        pendingAuthAction?.();
      }}
    />
  );
};

// Layout wrapper mirrors the <ScrollToTop /> and <GlobalLoginModal /> placement
// in lovable/src/App.tsx. createBrowserRouter requires these to live inside
// a layout route (they need router context from useLocation / useAuth).
// DraftProvider is placed here (inside the router) because DraftContext.tsx
// calls useNavigate(), which requires a router ancestor.
const RootLayout = () => (
  <DraftProvider>
    <ScrollToTop />
    <Outlet />
  </DraftProvider>
);

// Route list mirrors lovable/src/App.tsx exactly.
// The only intentional deviation: * catch-all uses UnderConstructionPage
// instead of NotFound, so unclaimed URLs get a styled fallback page.
// /blogs is aliased to Experiences to match Lovable's current routing.
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
  { path: "/",                    element: <Index /> },
  { path: "/trips",               element: <BrowseTrips /> },
  { path: "/trips/preview",       element: <TripPreview /> },
  { path: "/trips/:id",           element: <TripDetail /> },
  { path: "/create-trip",         element: <CreateTrip /> },
  { path: "/my-trips",            element: <MyTrips /> },
  { path: "/experiences",         element: <Experiences /> },
  { path: "/experiences/create",  element: <ExperienceCreate /> },
  { path: "/experiences/edit",    element: <ExperienceEdit /> },
  { path: "/experiences/:slug",   element: <ExperienceDetail /> },
  { path: "/blogs",               element: <Experiences /> },
  { path: "/travel-hosts",        element: <TravelHosts /> },
  { path: "/bookmarks",           element: <Bookmarks /> },
  { path: "/inbox",               element: <Inbox /> },
  { path: "/manage-trip/:id",     element: <ManageTrip /> },
  { path: "/login",               element: <Login /> },
  { path: "/signup",              element: <SignUp /> },
  { path: "/profile",             element: <Profile /> },
  { path: "/profile/:userId",     element: <Profile /> },
  { path: "*",                    element: <UnderConstructionPage /> },
  ]},
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <GlobalLoginModal />
          <RouterProvider router={router} />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
