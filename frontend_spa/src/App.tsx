import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { DraftProvider } from "@/contexts/DraftContext";

// All user-facing pages come from the Lovable source (@/ = lovable/src/).
// Never import page components from @frontend/pages except UnderConstructionPage.
import Index from "@/pages/Index";
import BrowseTrips from "@/pages/BrowseTrips";
import TripDetail from "@/pages/TripDetail";
import CreateTrip from "@/pages/CreateTrip";
import MyTrips from "@/pages/MyTrips";
import Login from "@/pages/Login";
import SignUp from "@/pages/SignUp";
import Profile from "@/pages/Profile";
import Blogs from "@/pages/Blogs";
import ManageTrip from "@/pages/ManageTrip";
import UnderConstructionPage from "@frontend/pages/UnderConstructionPage";

const queryClient = new QueryClient();

const router = createBrowserRouter([
  { path: "/",            element: <Index /> },
  { path: "/trips",       element: <BrowseTrips /> },
  { path: "/trips/:id",   element: <TripDetail /> },
  { path: "/create-trip", element: <CreateTrip /> },
  { path: "/my-trips",    element: <MyTrips /> },
  { path: "/blogs",            element: <Blogs /> },
  { path: "/manage-trip/:id",  element: <ManageTrip /> },
  { path: "/login",            element: <Login /> },
  { path: "/signup",      element: <SignUp /> },
  { path: "/profile",     element: <Profile /> },
  { path: "*",            element: <UnderConstructionPage /> },
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
