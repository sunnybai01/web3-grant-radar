import type { ReactNode } from "react";

import { TopNav } from "../../components/shell/top-nav";
import { Providers } from "../providers";

// The console's chrome and clients (React Query, CopilotKit) stay out of the
// landing page, which is static.
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <Providers>
      <TopNav />
      {children}
    </Providers>
  );
}
