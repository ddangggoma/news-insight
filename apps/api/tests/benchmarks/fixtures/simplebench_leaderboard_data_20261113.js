const leaderboardData = [
  { rank: "-",    model: "Highest Human Score*",             score: "95.4%", organization: "",            dateAdded: null },
  { rank: "1st", model: "Claude Fable 5.2",           score: "94.9%", organization: "Anthropic",   dateAdded: "2026-11-10" },
  { rank: "2nd", model: "Gemini 4 Carbon",            score: "92.6%", organization: "Google",      dateAdded: "2026-11-10" },
  { rank: "3rd", model: "Gemini 4 Argon",             score: "91.7%", organization: "Google",      dateAdded: "2026-11-10" },
  { rank: "4th", model: "Claude Opus 5.5",            score: "88.4%", organization: "Anthropic",   dateAdded: "2026-09-24" },
  { rank: "5th", model: "Claude Fable 5.1",           score: "86.6%", organization: "Anthropic",   dateAdded: "2026-09-03" },
  { rank: "6th", model: "GPT-6 Astra Pro",            score: "86.5%", organization: "OpenAI",      dateAdded: "2026-09-07" },
  { rank: "-",    model: "Human Baseline*",                  score: "83.7%", organization: "",            dateAdded: null },
  { rank: "7th", model: "GPT-6 Astra",                score: "83.6%", organization: "OpenAI",      dateAdded: "2026-09-07" },
  { rank: "8th", model: "GPT-6.1 Sol",                score: "82.9%", organization: "OpenAI",      dateAdded: "2026-10-01" },
  { rank: "9th", model: "Gemini 3.8 Flash",           score: "82.4%", organization: "Google",      dateAdded: "2026-09-03" },
  { rank: "10th", model: "Claude Fable",                     score: "81.9%", organization: "Anthropic",   dateAdded: "2026-06-10" },
  { rank: "11th", model: "Muse Spark 1.3",             score: "81.8%", organization: "Meta",        dateAdded: "2026-09-03" },
  { rank: "12th", model: "Claude Opus 5",           score: "80.6%", organization: "Anthropic",   dateAdded: "2026-07-24" },
  { rank: "110th", model: "Command R+",                       score: "17.4%", organization: "Cohere",      dateAdded: null },
  { rank: "111th", model: "GPT-4o mini",                      score: "10.7%", organization: "OpenAI",      dateAdded: null },
  { rank: "112th", model: "GPT-3.5 Turbo",                    score: "8.0%",  organization: "OpenAI",      dateAdded: null }
];

const openEndedData = [
  { rank: "1st", model: "Gemini 3.1 Pro Preview",         score: "64.8%", organization: "Google", dateAdded: "2026-02-17" },
  { rank: "2nd", model: "Claude Opus 4.7",                score: "62.9%", organization: "Anthropic", dateAdded: "2026-04-22" },
  { rank: "3rd", model: "Claude Opus 4.6",                score: "59.7%", organization: "Anthropic", dateAdded: "2026-02-17" }
];

// Pricing: USD per 1M tokens. Source: OpenRouter live model catalogue (openrouter.ai/api/v1/models).
// 'released' = OpenRouter listing date (proxy for public availability). est:true = delisted/experimental
// model priced from list price or nearest-tier proxy (see notes in build log), not a live OpenRouter quote.
const modelMeta = {
  "Claude Haiku 5.5":            { input:    0.1, output:     0.5, released: "2026-10-07", est: false, tout: 1085, cpr: 0.12 },
  "Gemini 4 Carbon":            { input:    2.0, output:    10.0, released: "2026-11-10", est: false, tout: 7456, cpr: 16.21 },
  "Gemini 4 Argon":             { input:    2.0, output:    10.0, released: "2026-10-13", est: false, tout: 520, cpr: 1.23 },
};
