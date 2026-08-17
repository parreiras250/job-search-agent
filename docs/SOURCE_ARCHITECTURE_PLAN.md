# Source Architecture Plan

Status: Etapas 13A–13F and 13G.1 implemented. Jobicy, Remotive, We Work
Remotely and Himalayas are registered as real global operational sources;
Greenhouse tenants are generated from the persistent Company Registry.

## Etapa 13B implemented foundation

The runtime now has an in-memory `SourceRegistry` whose ordered
`SourceDefinition` entries carry stable `source_id`, `source_family`,
`source_instance`, `SourceType`, immutable capabilities, factories, enablement,
priority and request budget. `MultiSourceDiscovery` iterates enabled definitions
without provider branches and keeps failure isolation, deterministic ordering and
the existing human-readable Jobicy/Remotive summaries.

Search execution accepts generic `SourceQuery` entries in addition to the two
legacy typed query collections. Contribution metrics use stable source IDs, and
capability, enablement and per-source request budget checks happen at the
execution boundary. The legacy fields remain temporarily to preserve the public
behavior of the current broad/full modes.

Normalized opportunities and SQLite schema version 4 store explicit source
identity. Lifecycle reconciliation compares exact `(source_family,
source_instance)` observations and no longer parses platform identity from a
display string. Existing Jobicy and Remotive rows receive an exact, idempotent
migration; unknown legacy labels are deliberately not guessed.

Offline contract tests exercise a third fictitious source, a fictitious tenant,
a feed, disabled definitions, five-source failure isolation, generic query
attribution and exact tenant lifecycle matching. No Greenhouse, Lever or other
new source was added to the operational registry.

### Adding a source in Etapa 13C+

1. Implement `JobSource.fetch()` and an adapter using documented/authorized
   access only.
2. Register one validated `SourceDefinition` with explicit identity,
   capabilities, attribution policy and conservative budget.
3. Add offline fixtures and contract tests for zero results, malformed payloads,
   partial failure, provenance and lifecycle authority.
4. Enable it only after legal/access review and a controlled validation. Tenant
   sources must use a distinct `source_instance` per tenant.

Durable multi-observation provenance, authoritative multi-source lifecycle,
company registry, automatic source discovery and normalized health history stay
deferred; 13B intentionally does not pretend those later controls are complete.

## Etapa 13C: first operational feed

We Work Remotely is the first real `FEED` registered through the generic
framework. Its sole default instance is `weworkremotely:sales-marketing`, backed
by the official public Sales and Marketing RSS and limited to one request. It is
enabled after Jobicy and Remotive in deterministic order.

The standard-library XML parser rejects DTD and oversized payloads and maps only
RSS fields that are present and trustworthy. The original WWR page URL remains
the primary job URL for attribution. Remote is confirmed by the board scope;
Brazil eligibility remains unknown unless existing geographic rules can infer it
from the item region.

WWR has `OBSERVATIONAL` lifecycle authority. Its exact structured identity
participates in the conservative miss policy, but it is not equivalent to a
future authoritative company ATS. No HTML scraping, pagination, extra category
feed or provider-specific scoring was introduced.

## Etapa 13D: persistent provenance implemented

SQLite schema version 5 separates the logical opportunity from its persistent
`source_observations`. Each observation stores stable source identity, type,
external ID or normalized observed URL, authority, first/last seen and checked
timestamps, active state and observation-level misses. The existing primary
source columns remain for compatibility and are not replaced merely because a
later observational source finds the same job.

Pipeline duplicate records now reach persistence: equivalent Jobicy, Remotive
and WWR candidates create one opportunity and multiple observations. Migration
backfills one deterministic observation per existing opportunity with
`INSERT OR IGNORE`, so reopening the database is idempotent and CRM/manual data
is untouched.

Lifecycle first updates observations for successful source instances. A source
failure never counts as absence. Any observation seen in the current run keeps
the opportunity open; global conservative misses advance only when every known
observation source completed successfully and none saw the job. A reappearance
through any source reopens the opportunity. `AUTHORITATIVE` is persisted and
tested with a fake future tenant, but no direct ATS source or aggressive
authority policy is enabled yet.

## Executive conclusion

The current architecture is safe and well tested for Jobicy plus Remotive, but
the orchestration model is structurally two-source. Adding sources one at a time
would spread platform names across discovery, strategy, lifecycle and metrics.
The next step should therefore be a small generic source framework before any
new integration.

The target model needs three different identities:

1. `source_family`: platform/protocol, such as `greenhouse`, `lever`, `jobicy`.
2. `source_definition`: configured discovery channel, such as `jobicy_broad`.
3. `source_instance`: tenant/feed being called, such as `greenhouse:acme`.

These must not be inferred from display strings.

## Current architecture audit

Priority means urgency before scaling: P0 blocks safe multi-source expansion;
P1 should follow in the first framework wave; P2 can remain compatible longer.

| Priority | File / symbol | Current behavior | Scaling risk | Recommended refactor |
|---|---|---|---|---|
| P0 | `discovery.py` — `MultiSourceDiscovery.__init__` | Owns exactly one Jobicy source and one Remotive source. | Every source adds constructor arguments, imports and tests to the central class. | Accept an ordered collection of registered `SourceExecution` definitions. |
| P0 | `discovery.py` — `MultiSourceDiscovery.run` | Builds a two-item tuple with names, source objects and adapters. | Central `if/import/tuple` grows linearly and prevents data-driven enable/disable. | Iterate registry definitions; keep failure isolation and stable ordering. |
| P0 | `agent.py` — `create_broad_discovery` | Requires exactly one query for each of two named fields. | A third source cannot join the weekly agent without editing the factory. | Resolve an enabled strategy through registry IDs and generic query plans. |
| P0 | `search_strategy.py` — `SearchStrategy` | Has `jobicy_queries` and `remotive_queries` fields and per-source limits. | Schema, validation and recommendation change for every source. | Store `queries_by_source_id` or an ordered tuple of generic query executions. |
| P0 | `search_strategy.py` — `MultiQueryDiscovery` | Imports two source classes/adapters and builds two list comprehensions. | Factories and adapters multiply inside orchestration. | Registry provides factory, adapter and query serializer. |
| P0 | `search_strategy.py` — `unique_by_source` | Initializes `{"Jobicy": 0, "Remotive": 0}` and classifies every non-Remotive job as Jobicy. | Metrics become incorrect immediately for a third source. | Build keys from executed definitions and attribute by explicit observation ID. |
| P0 | `lifecycle.py` — `_source_family` | Infers four families using substring checks in human source text. | Renaming, tenant labels or an unknown platform silently prevents/corrupts misses. | Store explicit family/instance observations; remove string parsing after migration. |
| P0 | `lifecycle.py` — `reconcile_lifecycle` | One primary opportunity has one source string; absence from that family can count as a miss. | An aggregator disappearance can close a job still present on its direct ATS. | Reconcile per observation; authoritative direct observations override aggregator absence. |
| P0 | `pipeline.py` / dedup flow | First equivalent input remains primary; duplicates are recorded only in the run result. | Input order can prefer an aggregator and durable provenance is lost. | Persist every observation and choose canonical fields using authority/quality priority. |
| P1 | `sources.py` | Each platform is a concrete class; transport protocol is reusable but metadata is not. | Capabilities, budgets, attribution and authority have nowhere canonical to live. | Keep source implementations, register their metadata in `SourceDefinition`. |
| P1 | `ingestion.py` | Each adapter embeds a display `source_name` string in `JobOpportunity.source`. | Display text doubles as identity and lifecycle key. | Adapter output should carry explicit source execution/observation metadata. |
| P1 | `search_strategy.py` — query classes | Jobicy and Remotive each require a dedicated dataclass. | Dozens of classes are possible even when query shapes overlap. | Generic `QueryPlan` with provider-specific validated parameters at the boundary. |
| P1 | `search_strategy.py` — marginal gain | Gain depends on sequential query/input order. | Cross-source attribution is biased toward the first source. | Report both ordered marginal gain and order-independent overlap/contribution metrics. |
| P1 | `repository.py` — `opportunities.source` | Stores one text source and one external ID. | Cannot represent the same job seen at ATS, board and aggregator simultaneously. | Add future `source_observations` table keyed to canonical opportunity. |
| P1 | `repository.py` — `agent_runs` | Stores lists of succeeded/failed source names as JSON. | Useful summary, but no source/tenant health history or latency. | Keep summary; add normalized run-source and run-instance metrics later. |
| P1 | `reports.py` / `reporting.py` | Formatting is mostly generic, but consumes current two-source discovery result. | Formats scale; upstream summary shape and very long source lists do not. | Consume generic execution summaries; group tenant failures compactly. |
| P1 | `weekly_run.py` | Overall status uses lists and aggregated ingestion errors. | Hundreds of tenant calls need thresholds, not “one tenant failed = whole run noisy”. | Define policy by source tier and failure ratio; still expose every failure in health data. |
| P2 | `sources.py` — base URLs and source names | Platform constants are intentionally concrete. | Not a problem inside plugins, but becomes clutter in one module. | Split implementations by family only after the registry contract stabilizes. |
| P2 | `agent.py` — `AgentRunResult` | Source lists and summary maps are generic enough, but field names reflect one discovery class. | Moderate coupling, no immediate correctness issue. | Preserve result shape while generalizing its producer. |
| P2 | tests/fixtures | Many tests assert exact Jobicy/Remotive ordering and names. | A big-bang refactor would be risky. | Keep compatibility fixtures; add registry-contract tests incrementally in 13B. |

`models.py`, `profiles.py`, career-fit rules and scoring do not require
source-specific changes. They should remain downstream of normalized jobs.

## Source taxonomy

The seven proposed labels mix scope, ownership and transport. A smaller primary
taxonomy is easier to apply:

| Proposed `source_type` | Meaning | Covers |
|---|---|---|
| `GLOBAL_BOARD` | One call/query searches a board-wide corpus. | Global, remote and LATAM boards. |
| `TENANT_BOARD` | Calls are scoped to one company/tenant. | ATS company boards and structured company career endpoints. |
| `FEED` | RSS/Atom/XML feed with feed semantics. | RSS feeds, including category feeds. |
| `AGGREGATOR` | Data is republished from other origins and is not authoritative. | Aggregator APIs; may also be global in scope. |

`COMPANY_CAREER_PAGE` is better represented as `TENANT_BOARD` plus an access
method (`JSON_API`, `XML`, `RSS`, or, only when explicitly permitted,
`STRUCTURED_HTML`). `REMOTE_JOB_BOARD` and `LATAM_JOB_BOARD` should be tags or
coverage metadata, not mutually exclusive types. `RSS_FEED` is a transport.

Keep `source_family` separate: it identifies the platform (`greenhouse`,
`lever`, `we_work_remotely`) and is stable across tenants. A future
`source_instance_id` identifies `greenhouse:company_x`.

## Source capabilities

A future immutable `SourceCapabilities` should describe facts needed for
orchestration, not every field a provider might return.

Recommended capabilities:

- scope: global or tenant-scoped;
- supported filters: query, location, category;
- pagination and maximum page size;
- stable external ID;
- description, posted date, salary and direct-apply URL availability;
- lifecycle authority level (`AUTHORITATIVE`, `OBSERVATIONAL`, `NONE`);
- authentication mode (`NONE`, `API_KEY`, `OAUTH`, `PARTNER_ONLY`);
- attribution/link-back requirement;
- request-cost hint and default timeout;
- whether one request is a complete snapshot for lifecycle purposes.

Avoid boolean explosion where an enum is clearer. For example,
`lifecycle_authority` is more useful than only `authoritative_for_lifecycle`, and
`authentication_mode` is better than `requires_auth`.

## Source registry

Conceptual contract:

```text
SourceDefinition
  id                    stable configuration ID
  display_name
  family                platform/protocol ID
  source_type
  enabled
  priority
  capabilities
  source_factory
  adapter_factory
  query_plans
  request_budget
  attribution_policy
  lifecycle_policy
```

The registry returns an ordered execution plan. Discovery must not know which
class belongs to which source. Configuration should be validated at startup:
unique IDs, compatible capabilities/query fields, nonnegative budgets and
available tenant identifiers. Secrets stay outside the registry rows and Git.

Initially, definitions can be Python configuration to keep 13B reversible.
SQLite-backed enable/disable should come only after the contract is proven.

## Company registry (implemented in 13F)

SQLite introduced this local operational state in schema version 6. The current
schema is version 7 after adding structured Himalayas restrictions. The implemented
record is intentionally compact and generic:

```text
tracked_companies
  id, company_key, company_name, careers_url
  ats_family, ats_identifier, enabled, priority
  remote_policy, latam_evidence
  notes, created_at, updated_at
  last_checked_at, last_success_at, failure_count
```

The source registry defines *how Greenhouse works*; the company registry defines
*which Greenhouse tenants to call*. The generic `ats_identifier` holds the
platform-specific public identifier without adding one column per ATS. Only
Greenhouse is executable in 13F. Other families remain stored and appear as
unsupported without generating requests or lifecycle misses.

Manual additions require a stable normalized `company_key`, display name, ATS
family and identifier. They can be enabled/disabled through a non-interactive
CLI. Future automatic discovery is still out of scope.

To avoid hundreds of unnecessary requests:

- prioritize companies with observed LATAM/remote evidence;
- rotate lower-priority tenants across weeks;
- back off repeated failures;
- skip tenants checked recently;
- use a total tenant request budget;
- promote companies that contribute incremental KEEP/REVIEW opportunities;
- demote, but do not delete, consistently empty/duplicate-only tenants.

## Global versus tenant execution

| Concern | Global board call | 100 ATS company calls |
|---|---|---|
| Unit of failure | Source/query | Tenant request |
| Request accounting | Usually 1–few per query/page | At least one per company, often paginated |
| Scheduling | Every weekly run if useful | Priority tiers and rotation |
| Health | Source-level | Family plus tenant-level |
| Reporting | One compact source row | Aggregate family row plus sampled/failed tenants |
| Lifecycle | Usually observational | Direct tenant snapshot can be authoritative |
| Efficiency | Gain per query/source | Gain per tenant and family |

A Greenhouse family outage should not create 100 unrelated noisy failures or
100 lifecycle misses. Conversely, one invalid tenant must not mark Greenhouse as
globally unavailable.

## Lifecycle authority and observations

Canonical opportunity and source observations must be separate concepts:

```text
opportunity X
  observation greenhouse:company (AUTHORITATIVE, seen this run)
  observation jobicy:broad       (OBSERVATIONAL, missing this run)
  observation remoteok:global    (OBSERVATIONAL, missing this run)
```

Recommended rules:

1. A successful authoritative direct ATS snapshot that contains the job confirms
   `OPEN`.
2. Aggregator absence never overrides a current authoritative `OPEN` signal.
3. An authoritative absence counts only after that exact tenant completed a
   trustworthy full snapshot.
4. When multiple authoritative instances exist, any current `OPEN` observation
   keeps the canonical opportunity open; closure requires policy agreement or
   exhaustion of all applicable authorities.
5. Without authoritative observations, use the existing conservative miss
   thresholds across successful observational sources, preferably requiring
   absence from all sources that previously observed the job.
6. Source failure, partial pagination or ingestion/persistence error cannot count
   as absence.

Never infer authority from URL/display text. Store observation timestamps,
external IDs, canonical URL, query/tenant provenance and snapshot completeness.

## Deduplication and provenance

“First wins” is deterministic only relative to input order. Future canonical
selection should prefer:

1. direct company ATS/career source;
2. trusted original job board;
3. aggregator.

Within a tier, prefer stable external ID, direct apply URL, full description and
freshness. Do not merge fields opportunistically without provenance. Persist all
observations so the system can answer where, when and under which query a job was
seen. The canonical opportunity remains the CRM identity; observations are
replaceable evidence.

## Source health

Persist per run/source/query/tenant:

- attempted/succeeded timestamps and latency;
- request/page counts;
- received, converted, warnings and errors;
- unique, KEEP and REVIEW contributions;
- duplicates and overlap;
- ordered incremental unique/KEEP gain;
- snapshot completeness and pagination state.

Derived metrics: success rate, duplicate rate, requests per incremental unique,
requests per relevant opportunity and p50/p95 latency. Tenant health must roll up
to family health without hiding individual failures.

Future CLI concept:

```text
sources list
sources disable remoteok
sources enable remoteok
companies disable COMPANY_ID
```

Enable/disable changes local configuration only. It must not delete history,
observations, CRM or credentials. Disabled authoritative instances must not
generate lifecycle misses.

## Request budget and cadence

The example `4 global + 100 Greenhouse + 100 Lever + 50 Ashby` is at least 254
requests before pagination, retries or detail calls. That is inappropriate as a
single unconditional weekly loop.

Proposed controls:

- hard total request budget per run;
- per-family and per-instance budgets;
- global P0 sources weekly; high-priority companies weekly; medium fortnightly;
  low-priority companies rotated monthly;
- pagination stops at both provider limit and local budget;
- bounded retries only for transient errors, with exponential backoff and jitter;
- no retry for validation, auth or clear 4xx tenant errors;
- explicit connect/read timeout;
- circuit breaker/backoff after consecutive tenant or family failures;
- record deferred work so “not attempted” is distinct from “failed” and “empty”.

Begin with a small pilot (for example 10–20 curated companies), measure gain,
then expand only when requests per relevant opportunity are acceptable.

## Success metrics

Raw received jobs is diagnostic, not success. Weekly and rolling four-run metrics:

- incremental unique opportunities versus the current two-source baseline;
- incremental KEEP and REVIEW;
- confirmed Brazil/LATAM/Worldwide eligible opportunities;
- requests per incremental unique and per KEEP+REVIEW;
- duplicate/overlap rate and source-pair overlap;
- source and tenant success rate;
- runtime and latency distribution;
- percentage with direct authoritative provenance;
- source contribution stability across runs.

## Rollout plan

### 13B — Generic Source Framework (exact next step)

Introduce contracts and an in-memory registry for the existing Jobicy and
Remotive only. Preserve all outputs and lifecycle behavior. Generalize discovery
iteration and source metrics; add compatibility tests. Do **not** add a source.

### 13C — We Work Remotely RSS integration (implemented)

Register the official Sales and Marketing feed as the third operational source,
with attribution, a one-request budget and observational lifecycle identity.

### 13D — Observation and provenance foundation (implemented)

Model explicit source IDs/families and durable observations before using direct
ATS authority. Migrate safely while preserving current `source` text.

### 13E — Greenhouse Direct ATS pilot (implemented)

Register the existing public Greenhouse source and adapter in generic discovery
for a manually configured set of at most five companies. Each company is an
independent `TENANT_BOARD` source, uses one request per run, reports health
separately and produces `AUTHORITATIVE` observations. Cross-source duplicates
remain one logical opportunity; an authoritative Greenhouse observation may
promote the automatic primary data while preserving internal identity, history
and manual CRM fields. No company registry, automatic tenant discovery, Lever
or Ashby integration is part of this pilot.

### 13F — Company Registry (implemented)

SQLite schema version 6 adds `tracked_companies`, manual CLI operations,
enable/disable, priority ordering and per-company health. Enabled Greenhouse
records generate authoritative tenant sources in generic discovery. Unsupported
families and disabled companies are skipped safely. A deterministic 25-tenant
cap prevents accidental scale; no automatic company discovery or bulk import is
included.

### 13G.1 — Himalayas Remote Jobs API (implemented)

Register Himalayas as the fourth global source. The operational plan performs
one official search request with `q=sales`, `sort=recent` and `page=1`. It does
not add a country filter because Brazil-only search would omit worldwide jobs
that may be eligible. The source is observational, requires attribution and
preserves structured salary, location restrictions and timezone restrictions.
Timezone data is persisted but has no scoring effect. The conceptual broad-run
budget is now Jobicy 4 maximum, Remotive 4 maximum, WWR 1 and Himalayas 1; the
default broad strategy uses one request from each source.

### 13G.2 — Remote/Global Wave 1 continuation

Measure Himalayas incremental gain before evaluating another documented source.
Arbeitnow, RemoteOK and Working Nomads remain out of scope.

### 13H — Lifecycle authority

Expand the authoritative lifecycle policy beyond the bounded Greenhouse pilot
only after provenance and snapshot completeness are proven for each source.

### 13I — ATS Wave 2

Evaluate Workable, SmartRecruiters, Recruitee and Personio; add only those with
verified zero-cost read access and meaningful company coverage.

### 13J — LATAM wave

Research and pilot the best verified structured LATAM source. Do not scrape
restricted sites to fill this gap.

## Non-goals and safety

The architecture must work with zero paid sources. Paid/partner-only APIs can be
optional but never dependencies. Do not automate logins, CAPTCHA solving,
Selenium/Playwright or brittle scraping for LinkedIn, Indeed, Glassdoor or
Google Jobs. No proposed source bypasses provider terms or attribution.
