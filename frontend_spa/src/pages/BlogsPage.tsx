import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Calendar, User } from "lucide-react";
import Footer from "@/components/Footer";
import { Card, CardContent } from "@/components/ui/card";
import FrontendNavbar from "@frontend/components/FrontendNavbar";
import { EmptyState, ErrorState, LoadingState } from "@frontend/components/PageState";
import { FrontendBlog, apiGet, apiUrl } from "@frontend/lib/api";

type BlogListPayload = {
  blogs: FrontendBlog[];
};

export default function BlogsPage() {
  const [payload, setPayload] = useState<BlogListPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<BlogListPayload>(apiUrl("blogs"))
      .then((nextPayload) => setPayload(nextPayload))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <FrontendNavbar />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <h1 className="mb-2 text-3xl font-bold text-foreground">Blogs</h1>
          <p className="mb-8 text-muted-foreground">Stories, tips, and experiences from the Tapne community.</p>

          {error ? <ErrorState title="Blogs unavailable" body={error} /> : null}
          {!payload && !error ? <LoadingState label="Loading live stories..." /> : null}
          {payload && payload.blogs.length === 0 ? (
            <EmptyState title="No blogs yet" body="Publish a blog post and it will appear here." />
          ) : null}
          {payload && payload.blogs.length > 0 ? (
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {payload.blogs.map((blog) => (
                <Link key={blog.slug} to={`/blogs/${blog.slug}`}>
                  <Card className="group overflow-hidden transition-shadow hover:shadow-lg">
                    <div className="relative aspect-[16/10] overflow-hidden">
                      <img
                        src={blog.cover_image_url || "/placeholder.svg"}
                        alt={blog.title}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    </div>
                    <CardContent className="p-4">
                      <h3 className="mb-2 line-clamp-2 text-base font-semibold leading-tight text-foreground transition-colors group-hover:text-primary">
                        {blog.title}
                      </h3>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <User className="h-3 w-3" />
                          {blog.author_display_name || blog.author_username || "Tapne"}
                        </div>
                        <div className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {blog.published_label || "Recently"}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      </main>
      <Footer />
    </div>
  );
}
