import type { ReaderItem } from "@/lib/reader-types";

export type CommentKind = "item" | "collection" | "dossier";

export interface TeamComment {
  id: number;
  body: string;
  author: string | null;
  created_at: string;
  mine: boolean;
}

export interface CollectionSummary {
  id: number;
  title: string;
  description: string | null;
  items: number;
  comments: number;
  created_by: string | null;
  updated_at: string;
}

export interface CollectionDetail extends CollectionSummary {
  entries: { item: ReaderItem; note: string | null; added_by: string | null; added_at: string }[];
}

export interface ItemTeam {
  comments: TeamComment[];
  collections: CollectionSummary[];
  all_collections: CollectionSummary[];
}
