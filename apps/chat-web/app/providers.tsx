"use client";

import { CopilotKit } from "@copilotkit/react-core/v2";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Toaster } from "../components/ui/toaster";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false },
          mutations: { retry: 0 },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <CopilotKit
        runtimeUrl="/api/copilotkit"
        useSingleEndpoint
        // The AG-UI inspector floats over the top bar and covers "Run scan".
        enableInspector={false}
        onError={(event) => {
          console.error("[copilotkit]", event);
        }}
      >
        {children}
        <Toaster />
      </CopilotKit>
    </QueryClientProvider>
  );
}
