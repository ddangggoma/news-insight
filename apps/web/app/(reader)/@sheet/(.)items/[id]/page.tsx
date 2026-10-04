import { ItemDetailView, loadItem } from "@/components/reader/item-detail";
import { ItemSheet } from "@/components/reader/item-sheet";

export default async function ItemSheetPage({ params }: { params: Promise<{ id: string }> }) {
  const detail = await loadItem((await params).id);
  return (
    <ItemSheet title={detail.item.title_ko ?? detail.item.title}>
      <ItemDetailView detail={detail} />
    </ItemSheet>
  );
}
