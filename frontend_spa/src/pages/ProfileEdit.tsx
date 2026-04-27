import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Loader2, Save, Eye, ArrowLeft } from "lucide-react";

const TRAVEL_TAGS = ["Backpacking", "Culture", "Trek", "Social", "Workation", "Beach", "Mountains", "Photography", "Food", "Wellness", "Adventure", "Road Trip", "Solo", "Luxury", "Budget"];

const ProfileEdit = () => {
  const { user, isAuthenticated, requireAuth, updateProfile } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isPreview = searchParams.get("mode") === "preview";
  const ownProfilePath = user?.username
    ? `/users/${user.username}`
    : user?.id
      ? `/users/${user.id}`
      : "/";

  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [location, setLocation] = useState("");
  const [website, setWebsite] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) requireAuth(() => {});
  }, [isAuthenticated, requireAuth]);

  useEffect(() => {
    if (user) {
      setName(user.name || "");
      setBio(user.bio || "");
      setLocation(user.location || "");
      setWebsite(user.website || "");
      setTags(user.travel_tags || []);
    }
  }, [user]);

  const toggleTag = (t: string) => setTags(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateProfile({ name, bio, location, website, travel_tags: tags });
      if (!updated) {
        toast.error("Could not save profile");
        return;
      }
      toast.success("Profile updated");
      navigate(ownProfilePath);
    } catch {
      toast.error("Could not save profile");
    } finally {
      setSaving(false);
    }
  };

  const togglePreview = () => {
    const next = new URLSearchParams(searchParams);
    if (isPreview) next.delete("mode");
    else next.set("mode", "preview");
    setSearchParams(next, { replace: false });
  };

  if (isPreview) {
    return (
      <div className="flex min-h-screen flex-col bg-background">
        <Navbar />
        <div className="border-b bg-yellow-50 px-4 py-3 text-center text-sm font-medium text-yellow-800">
          <Eye className="mr-1.5 inline h-4 w-4" />Private preview — visible only to you.
          <Button variant="ghost" size="sm" className="ml-3 h-7" onClick={togglePreview}>Back to edit</Button>
        </div>
        <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
          <div className="flex items-start gap-4">
            <Avatar className="h-20 w-20">
              <AvatarImage src={user?.avatar} />
              <AvatarFallback>{name[0]?.toUpperCase() || "?"}</AvatarFallback>
            </Avatar>
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-foreground">{name || "Your name"}</h1>
              {location && <p className="mt-1 text-sm text-muted-foreground">{location}</p>}
              {bio && <p className="mt-3 text-sm text-foreground">{bio}</p>}
              {tags.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {tags.map(t => <Badge key={t} variant="secondary">{t}</Badge>)}
                </div>
              )}
            </div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <Button variant="ghost" size="sm" onClick={() => navigate(ownProfilePath)} className="mb-4">
          <ArrowLeft className="mr-1.5 h-4 w-4" />Back to profile
        </Button>
        <h1 className="mb-6 text-2xl font-bold text-foreground">Edit Profile</h1>

        <Card>
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1.5">
              <Label>Display name</Label>
              <Input value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Bio</Label>
              <Textarea value={bio} onChange={e => setBio(e.target.value)} rows={4} />
            </div>
            <div className="space-y-1.5">
              <Label>Location</Label>
              <Input value={location} onChange={e => setLocation(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Website</Label>
              <Input value={website} onChange={e => setWebsite(e.target.value)} placeholder="https://" />
            </div>
            <div className="space-y-2">
              <Label>Travel tags</Label>
              <div className="flex flex-wrap gap-1.5">
                {TRAVEL_TAGS.map(t => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleTag(t)}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${tags.includes(t) ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background hover:bg-muted"}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 flex items-center gap-2">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}Save
          </Button>
          <Button variant="outline" onClick={togglePreview}>
            <Eye className="mr-1.5 h-4 w-4" />Preview
          </Button>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default ProfileEdit;
