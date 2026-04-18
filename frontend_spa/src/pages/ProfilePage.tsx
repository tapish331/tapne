import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Edit, MapPin } from "lucide-react";
import Footer from "@/components/Footer";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { ErrorState, LoadingState } from "@frontend/components/PageState";
import TripCarousel from "@frontend/components/TripCarousel";
import { FrontendTrip, apiGet, apiUrl } from "@frontend/lib/api";
import { useAuth } from "@frontend/context/AuthContext";

type ProfilePayload = {
  profile: {
    display_name: string;
    username: string;
    bio: string;
    location: string;
    website: string;
    email: string;
  } | null;
  created_trips: FrontendTrip[];
  joined_trips: FrontendTrip[];
};

export default function ProfilePage() {
  const { isAuthenticated, ready, updateProfile } = useAuth();
  const navigate = useNavigate();
  const [payload, setPayload] = useState<ProfilePayload | null>(null);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [location, setLocation] = useState("");
  const [website, setWebsite] = useState("");

  useEffect(() => {
    if (ready && !isAuthenticated) {
      navigate("/login");
      return;
    }
    if (!isAuthenticated) {
      return;
    }
    apiGet<ProfilePayload>(apiUrl("profile_me"))
      .then((nextPayload) => {
        setPayload(nextPayload);
        if (nextPayload.profile) {
          setDisplayName(nextPayload.profile.display_name);
          setBio(nextPayload.profile.bio);
          setLocation(nextPayload.profile.location);
          setWebsite(nextPayload.profile.website);
        }
      })
      .catch((err: Error) => setError(err.message));
  }, [ready, isAuthenticated, navigate]);

  if (!ready || (isAuthenticated && !payload && !error)) {
    return (
      <div className="flex min-h-screen flex-col">
        <FrontendNavbar />
        <main className="mx-auto flex w-full max-w-6xl flex-1 px-4 py-10">
          <LoadingState label="Loading profile..." />
        </main>
        <Footer />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col">
        <FrontendNavbar />
        <main className="mx-auto flex w-full max-w-6xl flex-1 px-4 py-10">
          <ErrorState title="Profile unavailable" body={error} />
        </main>
        <Footer />
      </div>
    );
  }

  if (!payload?.profile) {
    return null;
  }

  async function handleSave() {
    await updateProfile({
      display_name: displayName,
      bio,
      location,
      website,
    });
    setPayload((current) =>
      current
        ? {
            ...current,
            profile: {
              ...current.profile!,
              display_name: displayName,
              bio,
              location,
              website,
            },
          }
        : current,
    );
    setEditOpen(false);
  }

  const initial = payload.profile.display_name?.[0] || payload.profile.username?.[0] || "T";

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="mx-auto max-w-4xl px-4 py-8">
          <div className="mb-8 flex flex-col items-center gap-4 sm:flex-row sm:items-start">
            <Avatar className="h-20 w-20 ring-4 ring-primary/20">
              <AvatarFallback className="text-2xl">{initial}</AvatarFallback>
            </Avatar>
            <div className="flex-1 text-center sm:text-left">
              <h1 className="text-2xl font-bold text-foreground">{payload.profile.display_name}</h1>
              {payload.profile.location ? (
                <p className="mt-1 flex items-center justify-center gap-1 text-muted-foreground sm:justify-start">
                  <MapPin className="h-4 w-4" /> {payload.profile.location}
                </p>
              ) : null}
              {payload.profile.bio ? <p className="mt-2 max-w-md text-muted-foreground">{payload.profile.bio}</p> : null}
            </div>
            <Dialog open={editOpen} onOpenChange={setEditOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                  <Edit className="mr-1 h-4 w-4" /> Edit Profile
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Edit Profile</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-2">
                  <div>
                    <Label>Name</Label>
                    <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
                  </div>
                  <div>
                    <Label>Location</Label>
                    <Input value={location} onChange={(event) => setLocation(event.target.value)} />
                  </div>
                  <div>
                    <Label>Website</Label>
                    <Input value={website} onChange={(event) => setWebsite(event.target.value)} />
                  </div>
                  <div>
                    <Label>Bio</Label>
                    <Textarea rows={3} value={bio} onChange={(event) => setBio(event.target.value)} />
                  </div>
                  <Button className="w-full" onClick={() => void handleSave()}>
                    Save Changes
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          <TripCarousel
            title="Trips Hosted"
            trips={payload.created_trips}
            emptyLabel="You haven't hosted any trips yet."
          />
          <TripCarousel
            title="Trips Joined"
            trips={payload.joined_trips}
            emptyLabel="You haven't joined any trips yet."
          />
        </div>
      </main>
      <Footer />
    </div>
  );
}
