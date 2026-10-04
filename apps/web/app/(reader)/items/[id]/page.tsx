import type { Metadata } from "next";

import { ItemDetailView, loadItem } from "@/components/reader/item-detail";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { item } = await loadItem((await params).id);
  return { title: item.title_ko ?? item.title, description: item.summary_ko.join(" ") };
}

export default async function ItemPage({ params }: { params: Promise<{ id: string }> }) {
  const detail = await loadItem((await params).id);
  return (
    <main className="mx-auto max-w-2xl px-4 py-8 md:px-6">
      <ItemDetailView detail={detail} />
    </main>
  );
}
