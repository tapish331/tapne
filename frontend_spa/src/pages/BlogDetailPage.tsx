import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Calendar, User } from "lucide-react";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { ErrorState, LoadingState } from "@frontend/components/PageState";
import { FrontendBlog, apiGet, apiUrl } from "@frontend/lib/api";

type BlogDetailPayload = {
  blog: FrontendBlog;
};

export default function BlogDetailPage() {
  const { slug } = useParams();
  const [payload, setPayload] = useState<BlogDetailPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!slug) {
      return;
    }
    apiGet<BlogDetailPayload>(`${apiUrl("blogs")}${slug}/`)
      .then((nextPayload) => setPayload(nextPayload))
      .catch((err: Error) => setError(err.message));
  }, [slug]);

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="mx-auto max-w-4xl px-4 py-8">
          <Button variant="ghost" size="sm" asChild className="mb-4">
            <Link to="/blogs">
              <ArrowLeft className="mr-1 h-4 w-4" /> Back to blogs
            </Link>
          </Button>

          {error ? <ErrorState title="Blog unavailable" body={error} /> : null}
          {!payload && !error ? <LoadingState label="Loading story..." /> : null}
          {payload ? (
            <Card className="overflow-hidden">
              <div className="aspect-[16/7] overflow-hidden">
                <img
                  src={payload.blog.cover_image_url || "/placeholder.svg"}
                  alt={payload.blog.title}
                  className="h-full w-full object-cover"
                />
              </div>
              <CardContent className="space-y-5 p-6 md:p-8">
                <div className="space-y-3">
                  <h1 className="text-3xl font-bold text-foreground md:text-4xl">{payload.blog.title}</h1>
                  <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <User className="h-4 w-4" />
                      {payload.blog.author_display_name || payload.blog.author_username || "Tapne"}
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" />
                      {payload.blog.published_label || "Recently published"}
                    </span>
                  </div>
                </div>
                {payload.blog.excerpt ? <p className="text-lg text-muted-foreground">{payload.blog.excerpt}</p> : null}
                <div className="prose prose-slate max-w-none">
                  <p>{payload.blog.body || payload.blog.summary || "This story is being prepared."}</p>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </main>
      <Footer />
    </div>
  );
}
