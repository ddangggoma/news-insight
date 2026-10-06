// Classes for briefing sections that appear from a reading depth on (plan 13 C1). They live
// outside the "use client" depth component: a server component importing a constant from a
// client module gets a client reference, not the string.
export const FROM_FIVE = "group-data-[depth=one]/brief:hidden";
export const DEEP_ONLY = "group-data-[depth=one]/brief:hidden group-data-[depth=five]/brief:hidden";
