import { Suspense } from "react";

import { TriagePage } from "../features/triage/triage-page";

export default function Page() {
  // useSearchParams (triage view in the URL) needs a Suspense boundary.
  return (
    <Suspense>
      <TriagePage />
    </Suspense>
  );
}
