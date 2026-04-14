import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";
import { apiGet } from "@/lib/api";
import type { BlogData } from "@/types/api";
import { Loader2, Plus } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import ExperienceCard from "@frontend/components/ExperienceCard";

const Experiences = () => {
  const [blogs, setBlogs] = useState<BlogData[]>([]);
  const [loading, setLoading] = useState(true);
  const { isAuthenticated, requireAuth } = useAuth();

  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.blogs) { setLoading(false); return; }
    apiGet<{ blogs: BlogData[] }>(cfg.api.blogs)
      .then((data) => setBlogs(data.blogs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <div className="mb-8 flex items-end justify-between">
            <div>
              <h1 className="text-3xl font-bold text-foreground">Travel Experiences</h1>
              <p className="mt-1 text-muted-foreground">Stories, tips, and experiences from the Tapne community.</p>
            </div>
            <Button
              size="sm"
              onClick={() => {
                if (isAuthenticated) {
                  window.location.href = "/experiences/create";
                } else {
                  requireAuth(() => { window.location.href = "/experiences/create"; });
                }
              }}
            >
              <Plus className="mr-1 h-4 w-4" /> Write
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : blogs.length === 0 ? (
            <p className="py-12 text-center text-muted-foreground">No experiences shared yet. Be the first!</p>
          ) : (
            <div className="grid auto-rows-fr gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {blogs.map((blog) => (
                <ExperienceCard key={blog.slug} blog={blog} />
              ))}
            </div>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Experiences;
