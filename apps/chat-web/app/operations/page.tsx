import type { Metadata } from "next";

import { OperationsPage } from "../../features/operations/operations-page";

export const metadata: Metadata = { title: "Operations · Web3 Grant Radar" };

export default function Page() {
  return <OperationsPage />;
}
