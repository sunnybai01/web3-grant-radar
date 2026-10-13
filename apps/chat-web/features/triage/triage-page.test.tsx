// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";

import { makeItem, makeListing } from "@/test/fixtures";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/",
}));
vi.mock("@copilotkit/react-core/v2", () => ({ useFrontendTool: () => undefined }));
vi.mock("@copilotkit/react-ui", () => ({ CopilotChat: () => null }));
vi.mock("@/lib/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/client")>("@/lib/client");
  return {
    ...actual,
    client: {
      listOpportunities: vi.fn(),
      getOpportunity: vi.fn(),
      triageOpportunity: vi.fn(),
      deleteOpportunity: vi.fn(),
    },
  };
});

import { client } from "@/lib/client";

import { TriagePage } from "./triage-page";

const mocked = client as unknown as Record<string, ReturnType<typeof vi.fn>>;
const ITEMS = [makeItem(1, { title: "Base Builder Grants" }), makeItem(2, { title: "Sui Overflow" }), makeItem(3, { title: "Stellar SCF" })];

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
  Element.prototype.scrollIntoView = () => undefined;
});

beforeEach(() => {
  mocked.listOpportunities.mockImplementation(async (filters: { status: string }) =>
    makeListing(filters.status === "new" ? ITEMS : [])
  );
  mocked.getOpportunity.mockImplementation(async (id: number) => ({
    ...ITEMS.find((item) => item.id === id),
    description: "",
    sources: [],
  }));
  mocked.triageOpportunity.mockImplementation(async (id: number, status: string) => ({
    ...ITEMS.find((item) => item.id === id),
    triage_status: status,
  }));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TriagePage />
    </QueryClientProvider>
  );
}

const rows = () => within(screen.getByRole("listbox", { name: "Opportunities" })).getAllByRole("option");
const selectedTitle = () => screen.getByRole("article").getAttribute("aria-label");
const press = (key: string) => act(() => void fireEvent.keyDown(window, { key }));

it("lists New opportunities and selects the first one", async () => {
  renderPage();

  await waitFor(() => expect(rows()).toHaveLength(3));
  await waitFor(() => expect(selectedTitle()).toBe("Base Builder Grants"));
  expect(rows()[0].getAttribute("aria-selected")).toBe("true");
});

it("shortlists with S, moves to the next row, and undoes with Z", async () => {
  renderPage();
  await waitFor(() => expect(selectedTitle()).toBe("Base Builder Grants"));

  press("s");

  await waitFor(() => expect(mocked.triageOpportunity).toHaveBeenCalledWith(1, "shortlisted"));
  expect(rows().map((row) => row.textContent)).not.toContain(expect.stringContaining("Base Builder Grants"));
  expect(rows()).toHaveLength(2);
  expect(selectedTitle()).toBe("Sui Overflow");

  press("z");

  await waitFor(() => expect(mocked.triageOpportunity).toHaveBeenLastCalledWith(1, "new"));
  await waitFor(() => expect(rows()).toHaveLength(3));
  expect(rows()[0].textContent).toContain("Base Builder Grants");
});

it("J moves the selection and D dismisses the selected row", async () => {
  renderPage();
  await waitFor(() => expect(selectedTitle()).toBe("Base Builder Grants"));

  press("j");
  expect(selectedTitle()).toBe("Sui Overflow");

  press("d");
  await waitFor(() => expect(mocked.triageOpportunity).toHaveBeenCalledWith(2, "dismissed"));
  expect(selectedTitle()).toBe("Stellar SCF");
});

it("puts the row back when saving the decision fails", async () => {
  mocked.triageOpportunity.mockRejectedValueOnce(new Error("boom"));
  renderPage();
  await waitFor(() => expect(selectedTitle()).toBe("Base Builder Grants"));

  press("d");

  await waitFor(() => expect(rows()).toHaveLength(3));
  expect(selectedTitle()).toBe("Base Builder Grants");
});

it("says the list is done and when the next scan runs", async () => {
  mocked.listOpportunities.mockResolvedValue(makeListing([]));
  renderPage();

  expect(await screen.findByText("You're all caught up.")).toBeTruthy();
  expect(screen.getByText(/^Next scheduled scan at \d{2}:\d{2}\.$/)).toBeTruthy();
});


it("offers the apply page and the source separately", async () => {
  // Falling back to the source made 51 of 70 "apply" buttons open a tweet or an article.
  const withApply = makeItem(1, { title: "Base Builder Grants", apply_url: "https://base.org/apply", source_url: "https://x.com/base/status/1" });
  const sourceOnly = makeItem(2, { title: "Sui Overflow", apply_url: "", source_url: "https://news.example/sui" });
  mocked.listOpportunities.mockImplementation(async () => makeListing([withApply, sourceOnly]));
  mocked.getOpportunity.mockImplementation(async (id: number) => ({
    ...(id === 1 ? withApply : sourceOnly), description: "", sources: [],
  }));
  renderPage();

  await waitFor(() => expect(selectedTitle()).toBe("Base Builder Grants"));
  const detail = screen.getByRole("article");
  expect(within(detail).getByRole("link", { name: /apply page/i }).getAttribute("href")).toBe("https://base.org/apply");
  expect(within(detail).getByRole("link", { name: /source/i }).getAttribute("href")).toBe("https://x.com/base/status/1");

  press("j");
  await waitFor(() => expect(selectedTitle()).toBe("Sui Overflow"));
  const next = screen.getByRole("article");
  expect(within(next).queryByRole("link", { name: /apply page/i })).toBeNull();
  expect(within(next).getByRole("link", { name: /source/i }).getAttribute("href")).toBe("https://news.example/sui");
});
