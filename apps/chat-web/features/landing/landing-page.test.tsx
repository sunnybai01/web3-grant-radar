// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { copy } from "@/lib/copy";

import { LandingPage } from "./landing-page";

afterEach(cleanup);

it("sends its calls to action into the console", () => {
  render(<LandingPage />);

  const opens = screen.getAllByRole("link", { name: new RegExp(copy.landing.hero.cta, "i") });
  expect(opens.length).toBeGreaterThanOrEqual(3);
  opens.forEach((link) => expect(link.getAttribute("href")).toBe("/triage"));
  expect(screen.getByRole("link", { name: copy.landing.closing.secondary }).getAttribute("href")).toBe("/operations");
});

it("only links to sections that exist", () => {
  const { container } = render(<LandingPage />);

  const anchors = screen
    .getAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((href) => href.startsWith("#"));
  expect(anchors).toEqual(expect.arrayContaining(["#how", "#console"]));
  anchors.forEach((href) => expect(container.querySelector(href), href).not.toBeNull());
});

it("gives the typed headline its full text", () => {
  render(<LandingPage />);

  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(copy.landing.hero.title);
});
