import { Link } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { Button } from "@/components/ui/button";

export default function UnderConstructionPage() {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <Navbar />
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-24 text-center">
        <div className="max-w-md">
          <div className="text-6xl mb-6">🚧</div>
          <h1 className="text-3xl font-semibold text-foreground mb-3">
            Under Construction
          </h1>
          <p className="text-muted-foreground mb-8">
            This page is coming soon. Check back later.
          </p>
          <Button asChild>
            <Link to="/">Go Home</Link>
          </Button>
        </div>
      </main>
      <Footer />
    </div>
  );
}
