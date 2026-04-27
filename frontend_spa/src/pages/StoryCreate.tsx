import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import TiptapEditor from "@/components/TiptapEditor";
import StoryPreviewView from "@/components/StoryPreviewView";
import { useAuth } from "@/contexts/AuthContext";
import { apiPost } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Save, Eye, ArrowLeft, Send } from "lucide-react";

const STORY_INDEX_PATH = "/search?tab=stories";

const StoryCreate = () => {
  const { isAuthenticated, requireAuth, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isPreview = searchParams.get("mode") === "preview";

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [coverUrl, setCoverUrl] = useState("");
  const [location, setLocation] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) requireAuth(() => {});
  }, [isAuthenticated, requireAuth]);

  const handleSubmit = async (publish: boolean) => {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    setSaving(true);
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      const data = await apiPost<{ blog: { slug: string } }>(cfg.api.blogs, {
        title,
        short_description: description,
        cover_image_url: coverUrl,
        location,
        body: content,
        status: publish ? "published" : "draft",
      });
      toast.success(publish ? "Story published" : "Draft saved");
      const slug = data.blog?.slug;
      if (slug) navigate(`/stories/${slug}`);
      else navigate("/dashboard/stories");
    } catch {
      toast.error("Could not save story");
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
        <main className="flex-1">
          <StoryPreviewView title={title} description={description} coverUrl={coverUrl} content={content} location={location} authorName={user?.name} authorUsername={user?.username} />
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <Button variant="ghost" size="sm" onClick={() => navigate(STORY_INDEX_PATH)} className="mb-4">
          <ArrowLeft className="mr-1.5 h-4 w-4" />Cancel
        </Button>
        <h1 className="mb-6 text-2xl font-bold text-foreground">Write a story</h1>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Title</Label>
            <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Your story title" />
          </div>
          <div className="space-y-1.5">
            <Label>Short description</Label>
            <Textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} placeholder="A one-line teaser" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Cover image URL</Label>
              <Input value={coverUrl} onChange={e => setCoverUrl(e.target.value)} placeholder="https://..." />
            </div>
            <div className="space-y-1.5">
              <Label>Location</Label>
              <Input value={location} onChange={e => setLocation(e.target.value)} placeholder="Bali, Indonesia" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Story</Label>
            <TiptapEditor content={content} onChange={setContent} />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-2">
          <Button onClick={() => handleSubmit(true)} disabled={saving}>
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />}Publish
          </Button>
          <Button variant="outline" onClick={() => handleSubmit(false)} disabled={saving}>
            <Save className="mr-1.5 h-4 w-4" />Save draft
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

export default StoryCreate;
