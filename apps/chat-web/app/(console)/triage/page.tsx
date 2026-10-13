import type { Metadata } from "next";
import { Suspense } from "react";

import { TriagePage } from "../../../features/triage/triage-page";

export const metadata: Metadata = { title: "Triage · Web3 Grant Radar" };

export default function Page() {
  // useSearchParams (triage view in the URL) needs a Suspense boundary.
  return (
    <Suspense>
      <TriagePage />
    </Suspense>
  );
}
