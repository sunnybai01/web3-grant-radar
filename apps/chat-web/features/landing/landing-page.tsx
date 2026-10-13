import { ClosingCta } from "./closing-cta";
import { ConsoleSection } from "./console-section";
import { HeroSection } from "./hero-section";
import { HowItWorks } from "./how-it-works";
import { LandingFooter } from "./landing-footer";
import { LandingNav } from "./landing-nav";
import { SourceStrip } from "./source-strip";

/** The public front door at "/": what the radar does, and the way into the console. */
export function LandingPage() {
  return (
    <div className="min-h-screen bg-surface">
      <LandingNav />
      <main>
        <HeroSection />
        <SourceStrip />
        <HowItWorks />
        <ConsoleSection />
        <ClosingCta />
      </main>
      <LandingFooter />
    </div>
  );
}
