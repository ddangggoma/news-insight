BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='45s';
SELECT json_build_object('snapshot_at',now(),'items_total',(select count(*) from items),'oldest_seen',(select min(first_seen_at) from items),'newest_seen',(select max(first_seen_at) from items));
WITH a AS (
 SELECT i.source_id,count(*) n,count(distinct i.canonical_url) unique_urls,
 count(*) filter(where i.first_seen_at>now()-interval '24 hours') n24,
 count(*) filter(where i.published_at<i.first_seen_at-interval '30 days') old,
 count(*) filter(where i.published_at is null) no_date,
 count(*) filter(where c.status='ready') cards,
 count(*) filter(where c.status='ready' and c.scope in ('dx','dx_dependency') and c.taxonomy_revision like '2026-10-05.%' and (i.published_at is null or i.published_at>=i.first_seen_at-interval '30 days')) reader_eligible,
 count(*) filter(where c.scope='irrelevant') irrelevant
 FROM items i LEFT JOIN item_cards c ON c.item_id=i.id WHERE i.first_seen_at>now()-interval '7 days' GROUP BY 1
), f AS (SELECT source_id,count(*) attempts,count(*) filter(where outcome in ('success','not_modified')) ok FROM fetch_runs WHERE started_at>now()-interval '7 days' GROUP BY 1)
SELECT coalesce(jsonb_agg(t),'[]') FROM (
 SELECT s.key,s.name,s.track,s.category,s.access_method,s.official_domain,s.operator,s.region,s.language,s.endpoint_url,s.terms_url,s.storage_right,s.status,s.validation_stage,r.last_success_at,r.consecutive_failures,coalesce(a.n,0) items7d,coalesce(a.n24,0) items24h,a.unique_urls,a.old,a.no_date,a.cards,a.reader_eligible,a.irrelevant,f.attempts,f.ok
 FROM sources s LEFT JOIN a ON a.source_id=s.id LEFT JOIN f ON f.source_id=s.id LEFT JOIN source_runtimes r ON r.source_id=s.id ORDER BY s.key
) t;
SELECT coalesce(jsonb_agg(t),'[]') FROM (SELECT c.field,count(*) n FROM item_cards c JOIN items i ON i.id=c.item_id WHERE i.first_seen_at>now()-interval '7 days' AND c.status='ready' AND c.scope in ('dx','dx_dependency') AND c.taxonomy_revision like '2026-10-05.%' AND (i.published_at is null OR i.published_at>=i.first_seen_at-interval '30 days') GROUP BY 1 ORDER BY 2 DESC) t;
SELECT coalesce(jsonb_agg(t),'[]') FROM (SELECT s.key,i.title,i.url,i.published_at,c.field,c.themes FROM items i JOIN sources s ON s.id=i.source_id LEFT JOIN item_cards c ON c.item_id=i.id WHERE s.category='official_vendor' ORDER BY i.first_seen_at DESC LIMIT 20) t;
SELECT coalesce(jsonb_agg(t),'[]') FROM (SELECT briefing_date,status,jsonb_array_length(shortlist) shortlist_count FROM briefings ORDER BY briefing_date DESC,version DESC LIMIT 10) t;
WITH p AS (SELECT i.id,i.canonical_url,min(m.captured_at) first_metric,max(m.captured_at) last_metric,count(*) snapshots FROM items i JOIN item_metric_snapshots m ON m.item_id=i.id WHERE i.track='oss' GROUP BY 1,2) SELECT json_build_object('metric_items',count(*),'unique_urls',count(distinct canonical_url),'first_metric',min(first_metric),'last_metric',max(last_metric),'two_points',count(*) filter(where snapshots>=2),'seven_day_spans',count(*) filter(where last_metric-first_metric>=interval '7 days'),'thirty_day_spans',count(*) filter(where last_metric-first_metric>=interval '30 days')) FROM p;
SELECT json_build_object('n',count(*),'unique_urls',count(distinct canonical_url),'unique_hashes',count(distinct content_hash)) FROM items WHERE first_seen_at>now()-interval '7 days';
COMMIT;
