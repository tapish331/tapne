import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import TripCard from "@/components/TripCard";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import HeroSection from "@/components/home/HeroSection";
import QuickFilters from "@/components/home/QuickFilters";
import HorizontalCarousel from "@/components/home/HorizontalCarousel";
import CommunitySection from "@/components/home/CommunitySection";
import WhyTapne from "@/components/home/WhyTapne";
import TestimonialsSection from "@/components/home/TestimonialsSection";
import FAQSection from "@/components/home/FAQSection";
import FinalCTA from "@/components/home/FinalCTA";
import ExperienceCard from "@frontend/components/ExperienceCard";
import { apiGet } from "@/lib/api";
import type { HomeResponse, TripData, BlogData, CommunityProfile, TestimonialData } from "@/types/api";
import { MapPin, ArrowRight, Loader2 } from "lucide-react";

const Index = () => {
  const [trips, setTrips] = useState<TripData[]>([]);
  const [blogs, setBlogs] = useState<BlogData[]>([]);
  const [communityProfiles, setCommunityProfiles] = useState<CommunityProfile[]>([]);
  const [testimonials, setTestimonials] = useState<TestimonialData[]>([]);
  const [stats, setStats] = useState<{ travelers: number; trips_hosted: number; destinations: number } | undefined>();
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.home) { setLoading(false); return; }
    apiGet<HomeResponse>(cfg.api.home)
      .then((data) => {
        setTrips(data.trips || []);
        setBlogs(data.blogs || []);
        setCommunityProfiles(data.community_profiles || []);
        setTestimonials(data.testimonials || []);
        setStats(data.stats);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filteredTrips = useMemo(() => {
    if (!activeFilter) return trips;
    return trips.filter(
      (t) => (t.trip_type || "").toLowerCase() === activeFilter.toLowerCase()
    );
  }, [trips, activeFilter]);

  const destinations = useMemo(() => {
    const destMap = new Map<string, { name: string; image: string; count: number }>();
    trips.forEach((t) => {
      const dest = t.destination || "";
      const key = dest.split(",")[0].trim().toLowerCase();
      if (key) {
        const existing = destMap.get(key);
        if (existing) {
          existing.count++;
        } else {
          destMap.set(key, {
            name: key.charAt(0).toUpperCase() + key.slice(1),
            image: t.banner_image_url || "",
            count: 1,
          });
        }
      }
    });
    return Array.from(destMap.values());
  }, [trips]);

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex-1">
        {/* Hero — stats are rendered inside HeroSection below search */}
        <HeroSection trips={trips} stats={stats} />

        {/* 1. Explore Trips — filters live here */}
        <section className="mx-auto max-w-6xl px-4 py-10">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold text-foreground md:text-3xl">Explore Trips</h2>
              <p className="mt-1 text-muted-foreground">Discover community trips created by travelers.</p>
            </div>
            <Button variant="ghost" asChild className="hidden sm:flex">
              <Link to="/search">View all <ArrowRight className="ml-1 h-4 w-4" /></Link>
            </Button>
          </div>

          {/* Quick filter pills */}
          <QuickFilters active={activeFilter} onSelect={setActiveFilter} />

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : filteredTrips.length === 0 ? (
            <p className="py-12 text-center text-muted-foreground">
              {activeFilter ? `No ${activeFilter} trips available.` : "No trips available yet."}
            </p>
          ) : (
            <HorizontalCarousel>
              {filteredTrips.slice(0, 6).map((trip) => (
                <div key={trip.id} className="min-w-[300px] max-w-[320px] shrink-0">
                  <TripCard trip={trip} />
                </div>
              ))}
            </HorizontalCarousel>
          )}

          <div className="mt-6 text-center sm:hidden">
            <Button variant="outline" asChild>
              <Link to="/search">View All Trips</Link>
            </Button>
          </div>
        </section>

        {/* 2. Destinations */}
        {destinations.length > 0 && (
          <section className="py-14">
            <div className="mx-auto max-w-6xl px-4">
              <h2 className="mb-2 text-2xl font-bold text-foreground md:text-3xl">Explore Destinations</h2>
              <p className="mb-6 text-muted-foreground">Find trips by destination.</p>

              <HorizontalCarousel>
                {destinations.map((dest) => (
                  <Link
                    key={dest.name}
                    to={`/search?destination=${encodeURIComponent(dest.name)}&tab=trips`}
                    className="group w-[220px] shrink-0 sm:w-[260px]"
                  >
                    <Card className="overflow-hidden transition-shadow hover:shadow-lg">
                      <div className="relative aspect-[4/3] overflow-hidden">
                        {dest.image && (
                          <img
                            src={dest.image}
                            alt={dest.name}
                            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                          />
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                        <div className="absolute inset-x-0 bottom-0 p-4">
                          <div className="flex items-center gap-1.5 text-white">
                            <MapPin className="h-4 w-4" />
                            <span className="text-lg font-semibold">{dest.name}</span>
                          </div>
                          <p className="mt-0.5 text-xs text-white/80">
                            {dest.count} trip{dest.count !== 1 ? "s" : ""} available
                          </p>
                        </div>
                      </div>
                    </Card>
                  </Link>
                ))}
              </HorizontalCarousel>
            </div>
          </section>
        )}

        {/* 3. Travel Hosts */}
        <CommunitySection profiles={communityProfiles} />

        {/* 4. Travel Experiences */}
        {blogs.length > 0 && (
          <section className="bg-muted/30 py-14">
            <div className="mx-auto max-w-6xl px-4">
              <div className="mb-6 flex items-end justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-foreground md:text-3xl">Travel Experiences</h2>
                  <p className="mt-1 text-muted-foreground">Stories, tips, and experiences from fellow travelers.</p>
                </div>
                <Button variant="ghost" asChild className="hidden sm:flex">
                  <Link to="/search?tab=stories">View all <ArrowRight className="ml-1 h-4 w-4" /></Link>
                </Button>
              </div>

              <div className="grid auto-rows-fr gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {blogs.slice(0, 3).map((blog) => (
                  <ExperienceCard key={blog.slug} blog={blog} />
                ))}
              </div>
            </div>
          </section>
        )}

        {/* 5. Why Tapne */}
        <WhyTapne />

        {/* 6. What Travelers Say */}
        <TestimonialsSection testimonials={testimonials} />

        {/* 7. FAQ */}
        <FAQSection />

        {/* 8. Final CTA */}
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
};

export default Index;
