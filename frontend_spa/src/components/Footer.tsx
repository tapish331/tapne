import { Link } from "react-router-dom";
import logoSrc from "../assets/logo.png";

const Footer = () => (
  <footer className="border-t bg-card">
    <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-8 text-sm text-muted-foreground md:flex-row md:justify-between">
      <Link to="/" className="transition hover:opacity-90">
        <img src={logoSrc} alt="Tapne" className="h-10 w-auto rounded-sm" />
      </Link>
      <div className="flex gap-6">
        <Link to="/search" className="transition hover:text-foreground">Explore</Link>
        <Link to="/search?tab=stories" className="transition hover:text-foreground">Stories</Link>
        <Link to="/dashboard" className="transition hover:text-foreground">Dashboard</Link>
      </div>
      <div>© 2026 Tapne. All rights reserved.</div>
    </div>
  </footer>
);

export default Footer;
