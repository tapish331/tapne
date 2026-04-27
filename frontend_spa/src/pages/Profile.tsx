import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import type { TripData, BlogData } from "@/types/api";
import TripCard from "@/components/TripCard";
import HorizontalCarousel from "@/components/home/HorizontalCarousel";
import {
  MapPin, Edit, Loader2, Star, MessageCircle, Compass,
  Award, Users, Image as ImageIcon, Camera, X, Settings,
  AlertTriangle, Trash2, PauseCircle, UserPlus, UserCheck, CheckCircle2,
  Calendar,
} from "lucide-react";
import { toast } from "sonner";
import { useAuthStore } from "@/features/auth/store/useAuthStore";

interface ProfileResponse {
  profile: {
    username: string;
    display_name: string;
    email?: string;
    phone?: string;
    bio: string;
    location: string;
    website: string;
    avatar_url?: string;
    travel_tags?: string[];
    average_rating?: number;
    reviews_count?: number;
    trips_hosted?: number;
    travelers_hosted?: number;
    trips_joined?: number;
    followers_count?: number;
    is_following?: boolean;
  };
  trips_hosted: TripData[];
  trips_joined: TripData[];
  reviews: ReviewItem[];
  gallery: string[];
  stories?: BlogData[];
}

interface ReviewItem {
  id: number;
  reviewer_name: string;
  reviewer_avatar?: string;
  rating: number;
  text: string;
  trip_title: string;
  created_at: string;
}

const TRAVEL_TAG_OPTIONS = [
  "Backpacking", "Culture", "Trek", "Social", "Workation",
  "Beach", "Mountains", "Photography", "Food", "Wellness",
  "Adventure", "Road Trip", "Solo", "Luxury", "Budget",
];

function redirectToLoggedOutHome() {
  useAuthStore.getState().logout();
  if (window.TAPNE_RUNTIME_CONFIG?.session) {
    (window.TAPNE_RUNTIME_CONFIG as any).session.authenticated = false;
    (window.TAPNE_RUNTIME_CONFIG as any).session.user = null;
  }
  window.location.assign("/");
}

const Profile = () => {
  const { profileId: profileIdParam } = useParams<{ profileId: string }>();
  const userId = profileIdParam;
  const { user, isAuthenticated, updateProfile, requireAuth } = useAuth();
  const navigate = useNavigate();

  const [profileData, setProfileData] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editBio, setEditBio] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editTags, setEditTags] = useState<string[]>([]);
  const [editAvatar, setEditAvatar] = useState<string | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [isFollowing, setIsFollowing] = useState(false);
  const [followersCount, setFollowersCount] = useState(0);
  const [accountActionPending, setAccountActionPending] = useState(false);

  const isOwner = useMemo(() => {
    if (!user) return false;
    return String(user.id) === userId || user.username === userId;
  }, [user, userId]);

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    const profileId = userId || (user?.username ?? user?.id);
    if (!profileId) {
      setLoading(false);
      return;
    }

    apiGet<ProfileResponse>(`${cfg.api.base}/profile/${profileId}/`)
      .then((data) => {
        setProfileData(data);
        setIsFollowing(data.profile?.is_following ?? false);
        setFollowersCount(data.profile?.followers_count ?? 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [userId, user]);

  const p = profileData?.profile;
  const isHost = (p?.trips_hosted ?? 0) > 0;

  const openEdit = () => {
    if (!p) return;
    setEditName(p.display_name);
    setEditBio(p.bio);
    setEditLocation(p.location);
    setEditTags(p.travel_tags ?? []);
    setAvatarPreview(p.avatar_url || null);
    setEditAvatar(null);
    setEditOpen(true);
  };

  const handleAvatarUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setEditAvatar(reader.result as string);
      setAvatarPreview(reader.result as string);
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const toggleTag = (tag: string) => {
    setEditTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
  };

  const saveEdit = async () => {
    const updated = await updateProfile({
      name: editName,
      bio: editBio,
      location: editLocation,
      avatar: avatarPreview ?? undefined,
      travel_tags: editTags,
    });
    if (profileData && p) {
      const next = updated || {};
      setProfileData({
        ...profileData,
        profile: {
          ...p,
          display_name: next.display_name ?? editName,
          bio: next.bio ?? editBio,
          location: next.location ?? editLocation,
          travel_tags: next.travel_tags ?? editTags,
          avatar_url: next.avatar_url ?? avatarPreview ?? p.avatar_url,
        },
      });
    }
    toast.success("Profile updated!");
    setEditOpen(false);
  };

  const handleDeactivate = async () => {
    setAccountActionPending(true);
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      await apiPost(cfg.api.account_deactivate, {});
      toast.success("Account deactivated. You can reactivate anytime.");
      setDeactivateOpen(false);
      setSettingsOpen(false);
      redirectToLoggedOutHome();
    } catch {
      toast.error("Could not deactivate account. Please try again.");
      setAccountActionPending(false);
    }
  };

  const handleDeleteAccount = async () => {
    setAccountActionPending(true);
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      await apiPost(cfg.api.account_delete, {});
      toast.success("Account deletion scheduled. This cannot be undone.");
      setDeleteOpen(false);
      setSettingsOpen(false);
      redirectToLoggedOutHome();
    } catch {
      toast.error("Could not delete account. Please try again.");
      setAccountActionPending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </main>
        <Footer />
      </div>
    );
  }

  if (!p) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 items-center justify-center">
          <p className="text-muted-foreground">Profile not found.</p>
        </main>
        <Footer />
      </div>
    );
  }

  const reviews = profileData?.reviews ?? [];
  const gallery = profileData?.gallery ?? [];
  const tripsHosted = profileData?.trips_hosted ?? [];
  const tripsJoined = profileData?.trips_joined ?? [];
  const stories = [...(profileData?.stories ?? [])].sort((a, b) => {
    const ad = a.created_at ? new Date(a.created_at).getTime() : 0;
    const bd = b.created_at ? new Date(b.created_at).getTime() : 0;
    return bd - ad;
  });

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />

      <main className="flex-1">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:py-12">
          <div className="flex flex-col items-center gap-6 text-center sm:flex-row sm:items-start sm:text-left">
            <Avatar className="h-24 w-24 ring-4 ring-primary/20 sm:h-28 sm:w-28">
              <AvatarImage src={p.avatar_url} />
              <AvatarFallback className="bg-accent text-3xl font-semibold text-accent-foreground">
                {p.display_name?.[0]?.toUpperCase() ?? "?"}
              </AvatarFallback>
            </Avatar>

            <div className="flex-1 space-y-2">
              <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                <h1 className="text-2xl font-bold text-foreground">{p.display_name}</h1>
                {isHost && (
                  <Badge variant="secondary" className="gap-1 text-xs font-medium">
                    <Award className="h-3 w-3" /> Host
                  </Badge>
                )}
              </div>

              <p className="text-xs text-muted-foreground">@{p.username}</p>

              {p.location && (
                <p className="flex items-center justify-center gap-1 text-sm text-muted-foreground sm:justify-start">
                  <MapPin className="h-3.5 w-3.5" /> {p.location}
                </p>
              )}

              {p.bio && (
                <p className="max-w-md line-clamp-3 text-sm leading-relaxed text-muted-foreground">
                  {p.bio}
                </p>
              )}

              {p.travel_tags && p.travel_tags.length > 0 && (
                <div className="flex flex-wrap justify-center gap-1.5 pt-1 sm:justify-start">
                  {p.travel_tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="text-xs font-normal">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}

              {!isOwner && (
                <p className="flex items-center justify-center gap-1 pt-1 text-xs text-muted-foreground sm:justify-start">
                  <Users className="h-3 w-3" /> {followersCount} follower{followersCount !== 1 ? "s" : ""}
                </p>
              )}
            </div>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              icon={<Star className="h-4 w-4 text-yellow-500" />}
              label="Rating"
              value={p.average_rating ? `${p.average_rating.toFixed(1)}` : "—"}
              sub={p.reviews_count ? `${p.reviews_count} review${p.reviews_count !== 1 ? "s" : ""}` : "Not enough reviews"}
            />
            {isHost && (
              <>
                <StatCard icon={<Compass className="h-4 w-4 text-primary" />} label="Trips Hosted" value={String(p.trips_hosted ?? 0)} />
                <StatCard icon={<Users className="h-4 w-4 text-primary" />} label="Travelers Hosted" value={String(p.travelers_hosted ?? 0)} />
              </>
            )}
            <StatCard icon={<Compass className="h-4 w-4 text-primary" />} label="Trips Joined" value={String(p.trips_joined ?? 0)} />
          </div>

          <div className="mt-6 flex items-center justify-center gap-3 sm:justify-start">
            {isOwner ? (
              <>
                <Button variant="outline" size="sm" onClick={openEdit}>
                  <Edit className="mr-1 h-4 w-4" /> Edit Profile
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setSettingsOpen(true)}>
                  <Settings className="mr-1 h-4 w-4" /> Settings
                </Button>
              </>
            ) : (
              <>
                <Button
                  size="sm"
                  variant={isFollowing ? "secondary" : "default"}
                  onClick={() => {
                    if (!isAuthenticated) {
                      requireAuth();
                      return;
                    }
                    const cfg = window.TAPNE_RUNTIME_CONFIG;
                    const url = `${cfg.api.base}/profile/${p.username}/follow/`;
                    if (isFollowing) {
                      setIsFollowing(false);
                      setFollowersCount(c => c - 1);
                      apiDelete(url).catch(() => {
                        setIsFollowing(true);
                        setFollowersCount(c => c + 1);
                      });
                    } else {
                      setIsFollowing(true);
                      setFollowersCount(c => c + 1);
                      apiPost(url).catch(() => {
                        setIsFollowing(false);
                        setFollowersCount(c => c - 1);
                      });
                    }
                  }}
                >
                  {isFollowing ? <><UserCheck className="mr-1 h-4 w-4" /> Following</> : <><UserPlus className="mr-1 h-4 w-4" /> Follow</>}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!isAuthenticated) {
                      requireAuth();
                      return;
                    }
                    navigate(`/messages?dm=${p.username}`);
                  }}
                >
                  <MessageCircle className="mr-1 h-4 w-4" /> Message
                </Button>
              </>
            )}
          </div>

          <Tabs defaultValue="trips" className="mt-8">
            <TabsList className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="trips">Trips</TabsTrigger>
              <TabsTrigger value="reviews">Reviews</TabsTrigger>
              <TabsTrigger value="stories">Stories</TabsTrigger>
              <TabsTrigger value="gallery">Gallery</TabsTrigger>
            </TabsList>

            <TabsContent value="trips" className="mt-6 space-y-8">
              {tripsHosted.length > 0 && (
                <div>
                  <h2 className="mb-4 text-lg font-semibold text-foreground">Trips Hosted</h2>
                  <HorizontalCarousel>
                    {tripsHosted.map((t) => (
                      <div key={t.id} className="relative w-[280px] shrink-0 sm:w-[320px]">
                        <TripCard trip={t} />
                        {(t.status as string) === "completed" && (
                          <Badge variant="secondary" className="absolute right-2 top-2 z-10 text-xs">
                            <CheckCircle2 className="mr-1 h-3 w-3" /> Completed
                          </Badge>
                        )}
                      </div>
                    ))}
                  </HorizontalCarousel>
                </div>
              )}
              {tripsJoined.length > 0 && (
                <div>
                  <h2 className="mb-4 text-lg font-semibold text-foreground">Trips Joined</h2>
                  <HorizontalCarousel>
                    {tripsJoined.map((t) => (
                      <div key={t.id} className="relative w-[280px] shrink-0 sm:w-[320px]">
                        <TripCard trip={t} />
                        {(t.status as string) === "completed" && (
                          <Badge variant="secondary" className="absolute right-2 top-2 z-10 text-xs">
                            <CheckCircle2 className="mr-1 h-3 w-3" /> Completed
                          </Badge>
                        )}
                      </div>
                    ))}
                  </HorizontalCarousel>
                </div>
              )}
              {tripsHosted.length === 0 && tripsJoined.length === 0 && (
                <EmptyState message={isHost ? "No trips hosted yet" : "No trips yet"} cta={isHost ? { label: "Host your first trip", to: "/trips/new" } : undefined} />
              )}
            </TabsContent>

            <TabsContent value="reviews" className="mt-6">
              {reviews.length > 0 ? (
                <div className="space-y-4">
                  {reviews.map((r) => (
                    <Card key={r.id} className="overflow-hidden">
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          <Avatar className="h-9 w-9 shrink-0">
                            <AvatarImage src={r.reviewer_avatar} />
                            <AvatarFallback className="bg-accent text-xs text-accent-foreground">{r.reviewer_name[0]}</AvatarFallback>
                          </Avatar>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-foreground">{r.reviewer_name}</span>
                              <div className="flex items-center gap-0.5">
                                {Array.from({ length: 5 }).map((_, i) => (
                                  <Star key={i} className={`h-3 w-3 ${i < r.rating ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground/30"}`} />
                                ))}
                              </div>
                            </div>
                            <p className="mt-0.5 text-xs text-muted-foreground">{r.trip_title}</p>
                            <p className="mt-1.5 line-clamp-3 text-sm text-foreground/80">{r.text}</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              ) : (
                <EmptyState message="No reviews yet" />
              )}
            </TabsContent>

            <TabsContent value="stories" className="mt-6">
              {stories.length > 0 ? (
                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                  {stories.map((story) => (
                    <Link key={story.slug} to={`/stories/${story.slug}`} className="block">
                      <Card className="group overflow-hidden transition-shadow hover:shadow-lg">
                        {story.cover_image_url && (
                          <div className="relative aspect-[16/10] overflow-hidden">
                            <img src={story.cover_image_url} alt={story.title} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
                          </div>
                        )}
                        <CardContent className="p-4">
                          <h3 className="mb-1.5 line-clamp-2 text-base font-semibold leading-tight text-foreground transition-colors group-hover:text-primary">{story.title}</h3>
                          {(story.short_description || story.excerpt) && (
                            <p className="mb-2 line-clamp-2 text-xs text-muted-foreground">{story.short_description || story.excerpt}</p>
                          )}
                          {story.created_at && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Calendar className="h-3 w-3" />
                              {new Date(story.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </div>
              ) : (
                <EmptyState message="No stories shared yet" />
              )}
            </TabsContent>

            <TabsContent value="gallery" className="mt-6">
              {gallery.length > 0 ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {gallery.map((url, i) => (
                    <div key={i} className="aspect-square overflow-hidden rounded-xl">
                      <img src={url} alt="" className="h-full w-full object-cover" />
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState message="No photos yet" icon={<ImageIcon className="h-8 w-8 text-muted-foreground/40" />} />
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Profile</DialogTitle>
            <DialogDescription>Update your profile details below.</DialogDescription>
          </DialogHeader>
          <div className="space-y-5 pt-2">
            <div className="flex flex-col items-center gap-3">
              <div className="relative">
                <Avatar className="h-20 w-20">
                  <AvatarImage src={avatarPreview || undefined} />
                  <AvatarFallback className="bg-accent text-2xl text-accent-foreground">
                    {editName?.[0]?.toUpperCase() ?? "?"}
                  </AvatarFallback>
                </Avatar>
                <label className="absolute -bottom-1 -right-1 flex h-7 w-7 cursor-pointer items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md hover:bg-primary/90">
                  <Camera className="h-3.5 w-3.5" />
                  <input type="file" accept="image/*" className="hidden" onChange={handleAvatarUpload} />
                </label>
              </div>
              <p className="text-xs text-muted-foreground">Click camera to change photo</p>
            </div>

            <div>
              <Label>Name</Label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div>
              <Label>Location (City)</Label>
              <Input value={editLocation} onChange={(e) => setEditLocation(e.target.value)} placeholder="e.g. Mumbai" />
            </div>
            <div>
              <Label>Bio</Label>
              <Textarea value={editBio} onChange={(e) => setEditBio(e.target.value)} rows={3} maxLength={200} placeholder="A few words about you..." />
              <p className="mt-1 text-right text-xs text-muted-foreground">{editBio.length}/200</p>
            </div>

            <div>
              <Label>Travel Tags</Label>
              <p className="mb-2 text-xs text-muted-foreground">Select tags that describe your travel style</p>
              <div className="flex flex-wrap gap-2">
                {TRAVEL_TAG_OPTIONS.map(tag => (
                  <Badge
                    key={tag}
                    variant={editTags.includes(tag) ? "default" : "outline"}
                    className="cursor-pointer transition-colors"
                    onClick={() => toggleTag(tag)}
                  >
                    {tag}
                    {editTags.includes(tag) && <X className="ml-1 h-3 w-3" />}
                  </Badge>
                ))}
              </div>
            </div>

            {(p.email || p.username) && (
              <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Non-editable</p>
                {p.email && (
                  <div>
                    <Label className="text-xs text-muted-foreground">Email</Label>
                    <Input value={p.email} disabled className="bg-muted text-muted-foreground" />
                  </div>
                )}
                {p.phone && (
                  <div>
                    <Label className="text-xs text-muted-foreground">Phone</Label>
                    <Input value={p.phone} disabled className="bg-muted text-muted-foreground" />
                  </div>
                )}
                <div>
                  <Label className="text-xs text-muted-foreground">Username</Label>
                  <Input value={`@${p.username}`} disabled className="bg-muted text-muted-foreground" />
                </div>
              </div>
            )}

            <Button className="w-full" onClick={saveEdit}>Save Changes</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Account Settings</DialogTitle>
            <DialogDescription>Manage your account preferences.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 pt-2">
            <Button
              variant="outline"
              className="w-full justify-start gap-2"
              onClick={() => { setSettingsOpen(false); setDeactivateOpen(true); }}
            >
              <PauseCircle className="h-4 w-4 text-muted-foreground" />
              Deactivate Account
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-2 text-destructive hover:text-destructive"
              onClick={() => { setSettingsOpen(false); setDeleteOpen(true); }}
            >
              <Trash2 className="h-4 w-4" />
              Delete Account
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={deactivateOpen} onOpenChange={setDeactivateOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PauseCircle className="h-5 w-5 text-muted-foreground" /> Deactivate Account
            </DialogTitle>
            <DialogDescription>
              Your profile will be hidden and you won't receive notifications. You can reactivate anytime by logging back in.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDeactivateOpen(false)}>Cancel</Button>
            <Button variant="secondary" onClick={handleDeactivate} disabled={accountActionPending}>
              {accountActionPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Deactivate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" /> Delete Account
            </DialogTitle>
            <DialogDescription>
              This action cannot be undone. All your data, trips, and reviews will be permanently deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteAccount} disabled={accountActionPending}>
              {accountActionPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete Permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Footer />
    </div>
  );
};

function StatCard({
  icon, label, value, sub,
}: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <Card className="text-center">
      <CardContent className="flex flex-col items-center gap-1 px-3 py-4">
        {icon}
        <span className="text-xl font-bold text-foreground">{value}</span>
        <span className="text-xs text-muted-foreground">{label}</span>
        {sub && <span className="text-[10px] text-muted-foreground/70">{sub}</span>}
      </CardContent>
    </Card>
  );
}

function EmptyState({
  message, icon, cta,
}: { message: string; icon?: React.ReactNode; cta?: { label: string; to: string } }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      {icon}
      <p className="text-sm text-muted-foreground">{message}</p>
      {cta && (
        <Button size="sm" variant="outline" asChild>
          <Link to={cta.to}>{cta.label}</Link>
        </Button>
      )}
    </div>
  );
}

export default Profile;
