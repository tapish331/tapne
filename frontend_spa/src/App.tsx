import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@frontend/context/AuthContext";
import BlogDetailPage from "@frontend/pages/BlogDetailPage";
import BlogsPage from "@frontend/pages/BlogsPage";
import CreateTripPage from "@frontend/pages/CreateTripPage";
import HomePage from "@frontend/pages/HomePage";
import LoginPage from "@frontend/pages/LoginPage";
import MyTripsPage from "@frontend/pages/MyTripsPage";
import ProfilePage from "@frontend/pages/ProfilePage";
import SignupPage from "@frontend/pages/SignupPage";
import TripDetailPage from "@frontend/pages/TripDetailPage";
import TripsPage from "@frontend/pages/TripsPage";

function NotFoundPage() {
  return <Navigate to="/" replace />;
}

export default function App() {
  const router = createBrowserRouter([
    { path: "/", element: <HomePage /> },
    { path: "/trips", element: <TripsPage /> },
    { path: "/trips/:id", element: <TripDetailPage /> },
    { path: "/blogs", element: <BlogsPage /> },
    { path: "/blogs/:slug", element: <BlogDetailPage /> },
    { path: "/login", element: <LoginPage /> },
    { path: "/signup", element: <SignupPage /> },
    { path: "/profile", element: <ProfilePage /> },
    { path: "/create-trip", element: <CreateTripPage /> },
    { path: "/my-trips", element: <MyTripsPage /> },
    { path: "*", element: <NotFoundPage /> },
  ]);

  return (
    <TooltipProvider>
      <AuthProvider>
        <Toaster />
        <RouterProvider router={router} />
      </AuthProvider>
    </TooltipProvider>
  );
}
