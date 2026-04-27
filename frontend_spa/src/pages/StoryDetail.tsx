import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { apiGet, apiDelete } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { BlogData } from "@/types/api";
import { toast } from "sonner";
import { Loader2, Calendar, MapPin, Edit, ArrowLeft, Trash2 } from "lucide-react";
import { generateHTML } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import ImageExt from "@tiptap/extension-image";

const STORY_INDEX_PATH = "/search?tab=stories";

function renderBody(body?: string): string {
  if (!body) return "";
  try {
    const json = JSON.parse(body);
    if (json.type === "doc") return generateHTML(json, [StarterKit, ImageExt]);
  } catch {}
  return body;
}

const StoryDetail = () => {
  const { storyId } = useParams<{ storyId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [story, setStory] = useState<BlogData | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!story) return;
    if (!window.confirm("Delete this story permanently? This cannot be undone.")) return;
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.blogs) return;
    setDeleting(true);
    try {
      await apiDelete(`${cfg.api.blogs}${story.slug}/`);
      toast.success("Story deleted.");
      navigate(STORY_INDEX_PATH);
    } catch (err: any) {
      toast.error(err?.error || "Could not delete story. Please try again.");
      setDeleting(false);
    }
  };

  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.blogs || !storyId) {
      setLoading(false);
      return;
    }
    apiGet<{ blog: BlogData }>(`${cfg.api.blogs}${storyId}/`)
      .then((data) => setStory(data.blog || (data as any)))
      .catch((err) => { if (err?.status === 404) setNotFound(true); })
      .finally(() => setLoading(false));
  }, [storyId]);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </main>
        <Footer />
      </div>
    );
  }

  if (notFound || !story) {
    return (
      <div className="flex min-h-screen flex-col">
        <Navbar />
        <main className="flex flex-1 flex-col items-center justify-center px-4 text-center">
          <h1 className="text-2xl font-bold text-foreground">Story not found</h1>
          <p className="mt-2 text-muted-foreground">This story may have been removed.</p>
          <Button className="mt-4" onClick={() => navigate(STORY_INDEX_PATH)}>Back to stories</Button>
        </main>
        <Footer />
      </div>
    );
  }

  const html = renderBody(story.body);
  const isOwner = user?.username === story.author_username;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="flex-1">
        <article className="mx-auto max-w-[700px] px-4 py-8">
          <Button variant="ghost" size="sm" onClick={() => navigate(STORY_INDEX_PATH)} className="mb-4">
            <ArrowLeft className="mr-1.5 h-4 w-4" />All stories
          </Button>

          {story.cover_image_url && (
            <div className="mb-6 overflow-hidden rounded-xl">
              <img src={story.cover_image_url} alt={story.title} className="aspect-[2/1] w-full object-cover" />
            </div>
          )}

          <div className="mb-3 flex items-center justify-between gap-3">
            <h1 className="text-3xl font-bold leading-tight text-foreground md:text-4xl">{story.title}</h1>
            {isOwner && (
              <div className="flex shrink-0 items-center gap-2">
                <Button variant="outline" size="sm" asChild>
                  <Link to={`/stories/${story.slug}/edit`}><Edit className="mr-1.5 h-3.5 w-3.5" />Edit</Link>
                </Button>
                <Button variant="outline" size="sm" onClick={handleDelete} disabled={deleting} className="border-destructive/30 text-destructive hover:bg-destructive/5 hover:text-destructive">
                  {deleting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1.5 h-3.5 w-3.5" />}
                  Delete
                </Button>
              </div>
            )}
          </div>

          {story.short_description && (
            <p className="mb-4 text-base leading-relaxed text-muted-foreground">{story.short_description}</p>
          )}

          <div className="mb-6 flex flex-wrap items-center gap-4">
            <Link to={`/users/${story.author_username}`} className="flex items-center gap-2 hover:opacity-80">
              <Avatar className="h-8 w-8">
                <AvatarFallback className="bg-accent text-xs">{(story.author_display_name || story.author_username || "?")[0]?.toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="text-sm font-medium text-foreground">{story.author_display_name || story.author_username}</span>
            </Link>
            {story.created_at && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Calendar className="h-3 w-3" />
                {new Date(story.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
              </div>
            )}
            {story.location && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <MapPin className="h-3 w-3" />{story.location}
              </div>
            )}
          </div>

          {story.tags && story.tags.length > 0 && (
            <div className="mb-6 flex flex-wrap gap-1.5">
              {story.tags.map(t => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}
            </div>
          )}

          <div
            className="prose prose-neutral max-w-none text-foreground/90 dark:prose-invert [&_img]:my-4 [&_img]:rounded-lg"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </article>
      </main>
      <Footer />
    </div>
  );
};

export default StoryDetail;
