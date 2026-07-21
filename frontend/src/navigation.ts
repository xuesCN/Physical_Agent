import { useCallback, useEffect, useState } from "react";

export const PAGE_KEYS = [
  "chat",
  "overview",
  "actions",
  "state",
  "hardware",
  "memory",
  "events",
  "settings"
] as const;

export type PageKey = (typeof PAGE_KEYS)[number];

const DEFAULT_PAGE: PageKey = "overview";
const PAGE_QUERY_PARAMETER = "page";
const PAGE_KEY_SET = new Set<string>(PAGE_KEYS);

interface PageSelection {
  page: PageKey;
  rawPage: string | null;
  valid: boolean;
}

function readPageSelection(): PageSelection {
  const rawPage = new URLSearchParams(window.location.search).get(PAGE_QUERY_PARAMETER);
  if (rawPage && PAGE_KEY_SET.has(rawPage)) {
    return { page: rawPage as PageKey, rawPage, valid: true };
  }
  return { page: DEFAULT_PAGE, rawPage, valid: rawPage === null };
}

function pageUrl(page: PageKey): string {
  const url = new URL(window.location.href);
  url.searchParams.set(PAGE_QUERY_PARAMETER, page);
  return `${url.pathname}${url.search}${url.hash}`;
}

export function usePageNavigation(): readonly [PageKey, (page: PageKey) => void] {
  const [activePage, setActivePage] = useState<PageKey>(() => readPageSelection().page);

  useEffect(() => {
    const syncFromUrl = () => {
      const selection = readPageSelection();
      if (!selection.valid) {
        window.history.replaceState(window.history.state, "", pageUrl(DEFAULT_PAGE));
      }
      setActivePage(selection.page);
    };

    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  const navigate = useCallback((page: PageKey) => {
    const selection = readPageSelection();
    if (selection.valid && selection.page === page) {
      setActivePage(page);
      return;
    }

    window.history.pushState(null, "", pageUrl(page));
    setActivePage(page);
  }, []);

  return [activePage, navigate] as const;
}
