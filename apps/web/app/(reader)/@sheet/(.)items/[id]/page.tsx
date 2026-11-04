import { ItemDetailView, loadItem } from "@/components/reader/item-detail";
import { ItemDialog } from "@/components/reader/item-dialog";

export default async function ItemDialogPage({ params }: { params: Promise<{ id: string }> }) {
  const detail = await loadItem((await params).id);
  return (
    <ItemDialog id={detail.item.id} url={detail.item.url} title={detail.item.title_ko ?? detail.item.title}>
      <ItemDetailView detail={detail} />
    </ItemDialog>
  );
}
