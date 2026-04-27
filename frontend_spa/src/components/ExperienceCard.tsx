import { Link } from "react-router-dom";
import { Calendar, User } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { BlogData } from "@/types/api";

const EXPERIENCE_FALLBACK_IMAGE =
  "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=80";

function formatPublishedDate(iso?: string): string {
  if (!iso) {
    return "Recently";
  }
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ExperienceCard({ blog }: { blog: BlogData }) {
  const excerpt = blog.short_description || blog.excerpt || "A Tapne community story.";
  const coverImage = blog.cover_image_url || EXPERIENCE_FALLBACK_IMAGE;

  return (
    <Link to={`/stories/${blog.slug}`} className="block h-full">
      <Card className="group flex h-[360px] flex-col overflow-hidden transition-shadow hover:shadow-lg">
        <div className="relative aspect-[16/10] shrink-0 overflow-hidden bg-muted">
          <img
            src={coverImage}
            alt={blog.title}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        </div>
        <CardContent className="flex flex-1 flex-col p-4">
          <div className="space-y-2">
            <h3 className="line-clamp-2 text-base font-semibold leading-tight text-foreground transition-colors group-hover:text-primary">
              {blog.title}
            </h3>
            <p className="line-clamp-3 text-sm text-muted-foreground">{excerpt}</p>
          </div>
          <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-xs text-muted-foreground">
            <div className="flex min-w-0 items-center gap-1">
              <User className="h-3 w-3 shrink-0" />
              <span className="truncate">{blog.author_display_name || blog.author_username || "Tapne"}</span>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Calendar className="h-3 w-3" />
              <span>{formatPublishedDate(blog.created_at)}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
