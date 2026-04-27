import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";

const FinalCTA = () => {
  const navigate = useNavigate();
  const { requireAuth } = useAuth();
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 text-center">
      <h2 className="mb-4 text-2xl font-bold text-foreground md:text-3xl">
        Find your kind of people
      </h2>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button asChild size="lg" className="rounded-full">
          <Link to="/search">Explore Trips</Link>
        </Button>
        <Button
          variant="outline"
          size="lg"
          className="rounded-full"
          onClick={() => requireAuth(() => navigate("/trips/new"))}
        >
          Host a Trip
        </Button>
      </div>
    </section>
  );
};

export default FinalCTA;
