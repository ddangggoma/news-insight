import "server-only";

import { notFound } from "next/navigation";

import { DomainPage } from "@/components/reader/domain/domain-view";
import { ApiError } from "@/lib/api";
import { DOMAIN_META, type DomainKind, type DomainView, domainQuery, parseDomainState } from "@/lib/domain-types";
import type { SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";

/**
 * The /research and /patents pages: the state from the address, the tab's API view, the page.
 * An unknown field or company is a missing page; any other API failure reaches the reader
 * error page (app/(reader)/error.tsx).
 */
export async function renderDomainPage(domain: DomainKind, searchParams: Promise<SearchParams>) {
  await requireUser();
  const state = parseDomainState(domain, await searchParams);
  let view: DomainView;
  try {
    view = await readerGet<DomainView>(DOMAIN_META[domain].api, domainQuery(domain, state), REVALIDATE.domain);
  } catch (error) {
    if (error instanceof ApiError && [404, 422].includes(error.status)) notFound();
    throw error;
  }
  return <DomainPage view={view} state={state} />;
}
