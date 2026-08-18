# Ashby tenant expansion research — Etapa 13H.5

Research date: 2026-08-18. This document is a selection study, not runtime
configuration. No tenant below is registered by this stage.

## Method and evidence boundary

The technical source of truth is Ashby's official
[Public Job Posting API](https://developers.ashbyhq.com/docs/public-job-posting-api).
It documents:

- board identifier: the final segment of `https://jobs.ashbyhq.com/{board}`;
- one unauthenticated `GET` to
  `https://api.ashbyhq.com/posting-api/job-board/{board}`;
- optional `includeCompensation=true`;
- all currently published postings in one `jobs` list; no pagination is
  documented;
- title, location and secondary locations, department/team, `isRemote`,
  `workplaceType`, plain/HTML description, ISO `publishedAt`, employment type,
  postal address, job/apply URLs and optional compensation;
- missing source data remains missing. The page documents no rate limit or
  attribution requirement.

Candidate discovery was deliberately bounded. Twenty-five guessed board URLs
were checked only to distinguish a real organization page from Ashby's generic
not-found page. Fifteen were confirmed by organization metadata on the public
Ashby page and form the evaluated set below. The Posting API was **not** called
for these candidates, there was no recursive link traversal, and no company was
accepted merely because a guessed URL returned HTTP 200.

Current-title evidence below is a point-in-time research signal from the public
board page, not a promise that a role remains open. `Remote` alone never proves
Brazil eligibility.

## Evaluation vocabulary

- Geography: `BRAZIL_CONFIRMED`, `LATAM_CONFIRMED`, `GLOBAL_CONFIRMED`,
  `POSSIBLE`, `UNCLEAR`, or `INCOMPATIBLE`.
- Sales density: `HIGH`, `MEDIUM`, or `LOW`, based on the current title mix,
  not a complete historical count.
- Priority combines geography fit, sales density, remote compatibility,
  company/role quality and expected incremental coverage. It is research-only:
  `P0`, `P1`, `P2`, or `DEFER`.

## Evidence table — 15 confirmed tenants

| Tenant | Board identifier | Organization | Type | Brazil/LATAM evidence | Remote evidence | Sales/GTM evidence | Current relevant example | Priority | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| [ElevenLabs](https://jobs.ashbyhq.com/elevenlabs) | `elevenlabs` | ElevenLabs | Company tenant | **BRAZIL_CONFIRMED**: current Brazil and LATAM titles/locations | Remote locations coexist with country-specific restrictions; evaluate each job | **HIGH**: AE, AM, SDR, partnerships, solutions | `Strategic Account Executive - Brazil`; also LATAM SDR/AM/Solutions roles | **P0** | Wave 1 |
| [Replit](https://jobs.ashbyhq.com/replit) | `replit` | Replit | Company tenant | **BRAZIL_CONFIRMED**: explicit current Brazil role/location | Mixed: Brazil plus separately restricted UK/Japan/Europe roles | **HIGH**: AE, BDR, AM, partnerships | `Account Executive (Brazil)` | **P0** | Wave 1 |
| [Vanta](https://jobs.ashbyhq.com/vanta) | `vanta` | Vanta | Company tenant | **POSSIBLE**: `Account Executive, LatAm` is territorial evidence, not by itself worker-location proof | Many remote listings are explicitly US or other regions | **HIGH** | `Account Executive, LatAm` | **P1** | Validate exact location payload before pilot |
| [Deel](https://jobs.ashbyhq.com/deel) | `Deel` | Deel | Company tenant | **POSSIBLE**: global employment product and distributed hiring are promising, but no current Brazil role was verified in this pass | Ashby board is real but routes candidates to Deel's custom careers surface | Likely high; current Ashby title list was not available in the inspected page | None safely verified | **P1** | Shape-check one official API response before considering Wave 2 |
| [Supabase](https://jobs.ashbyhq.com/supabase) | `supabase` | Supabase | Company tenant | **UNCLEAR**: current GTM examples were APAC/EMEA, not Brazil/LATAM | **GLOBAL_CONFIRMED for remote work**, but role eligibility remains regional | **MEDIUM**: partnerships and AE roles | `Partnerships Manager, Ecosystem`; APAC AE | **P1** | Monitor, not Wave 1 |
| [ClickHouse](https://jobs.ashbyhq.com/clickhouse) | `clickhouse` | ClickHouse | Company tenant | **UNCLEAR**: broad international footprint, no current Brazil/LATAM sales location confirmed | Distributed locations, frequently territory-specific | **HIGH**: commercial/enterprise AE, RevOps, TAM | `Commercial Account Executive` | **P1** | Monitor for explicit LATAM/Brazil openings |
| [incident.io](https://jobs.ashbyhq.com/incident) | `incident` | incident.io | Company tenant | **UNCLEAR**: no Brazil/LATAM worker-location evidence verified | Remote/distributed evidence is not enough to infer Brazil | **HIGH**: BDR, commercial/strategic AE, CSM, Solutions | `Commercial Account Executive` | **P1** | Wave 2 only after geography proof |
| [Mercury](https://jobs.ashbyhq.com/mercury) | `mercury` | Mercury | Company tenant | **UNCLEAR** | Real Ashby tenant; current list was not exposed in the inspected board shell | Historically plausible fintech GTM, not current evidence | None safely verified | **P2** | Recheck only if an explicit LATAM role appears |
| [Airbyte](https://jobs.ashbyhq.com/airbyte) | `airbyte` | Airbyte | Company tenant | **INCOMPATIBLE in current sample**: commercial roles were US/San Francisco | Some remote roles, but current sales examples were US-bound | **HIGH** | `Enterprise Account Executive` — United States | **DEFER** | Do not spend weekly request now |
| [Linear](https://jobs.ashbyhq.com/linear) | `linear` | Linear | Company tenant | **INCOMPATIBLE in current sample**: GTM roles were North America/Europe | Distributed, but current roles are region-limited | **HIGH**: AE, CSM, RevOps, Solutions | `Account Executive, Enterprise` — North America | **DEFER** | Do not pilot without LATAM opening |
| [Attio](https://jobs.ashbyhq.com/attio) | `attio` | Attio | Company tenant | **INCOMPATIBLE in current sample**: sales roles were US/UK | European/US location flexibility, not Brazil | **HIGH**: AE, partnerships, CSM, pre/post-sales | `Account Executive` — SF/NY/London | **DEFER** | No weekly request |
| [Ashby](https://jobs.ashbyhq.com/ashby) | `Ashby` | Ashby | Company tenant | **INCOMPATIBLE in current sample**: remote US/Canada/EU | Remote-first, explicitly region-bound | **HIGH** | `Enterprise Account Executive - Americas`, located US/Canada | **DEFER** | “Americas” must not override worker-location restrictions |
| [Perplexity](https://jobs.ashbyhq.com/perplexity) | `perplexity` | Perplexity | Company tenant | **INCOMPATIBLE in current sample**: remote GTM roles were US or APAC | Remote often explicitly United States | **HIGH**: AE, BDR, CSM, RevOps | `Commercial Account Executive` — Remote US | **DEFER** | No weekly request |
| [Ramp](https://jobs.ashbyhq.com/ramp) | `ramp` | Ramp | Company tenant | **INCOMPATIBLE in current sample**: US/Canada-heavy | Remote is explicitly US/Canada | **HIGH**: extensive AE/AM/BD/CS/partnerships | `Account Manager | Commercial` — Remote US | **DEFER** | High density does not compensate for geography |
| [Railway](https://jobs.ashbyhq.com/railway) | `Railway` | Railway | Company tenant | **GLOBAL_CONFIRMED** for several technical roles | Global and US-remote listings coexist | **LOW** for target GTM in current sample | No current target sales role verified | **P2** | Monitor; low expected relevant yield |

## Candidate groups

### Group A — LATAM / remote recruiting

LatamCent remains the only confirmed recruiting publisher in this bounded
sample. No second agency-style Ashby board met all three gates: confirmed board
identity, multi-employer/recruiting semantics, and current LATAM/GTM evidence.
This is a useful negative result: company boards must not be mislabeled as
recruiting boards merely because they have many international openings.

### Groups B–D — company tenants

- Remote-first SaaS: Deel, Supabase, Linear and Railway. Only Railway provided
  clear global locations in the current sample, but its target-role density was
  low. Remote-first did not imply Brazil eligibility.
- High-value sales employers: ElevenLabs, Replit, Vanta, ClickHouse,
  incident.io, Airbyte, Linear, Attio, Perplexity and Ramp. Geography removes
  most from immediate pilot consideration.
- Brazil/LATAM expansion: ElevenLabs and Replit have the strongest worker-role
  evidence. Vanta has a LATAM territory title but needs exact location
  validation before registration.

## Publisher versus employer

A company tenant belongs to the actual employer, so a future configured
`employer_name` can truthfully name that organization after validation. A
recruiting tenant belongs to an agency/publisher and may contain confidential or
multiple client employers; the adapter must retain an undisclosed-employer label
unless the official contract provides the client identity.

This distinction affects display, naming and future registry ownership:

| Dimension | Company tenant | Recruiting tenant |
|---|---|---|
| Publisher | Employer itself | Agency or recruiting board |
| Employer field | Configured organization, after verification | Unknown unless officially supplied per posting |
| Suggested identity | `ashby:<company-key>` | `ashby:<publisher-key>` |
| Lifecycle | Candidate for authoritative observation only after snapshot completeness is proven | Observational by default |
| Registry future | Company Registry may eventually own it | Source Registry is the safer current home |

No architecture changes are proposed in 13H.5.

## Recommended Wave 1

Start with **exactly two new tenants**, not five, because only two currently have
strong worker-location evidence:

1. **ElevenLabs (`elevenlabs`)** — Brazil/LATAM AE, AM, SDR and Solutions
   evidence; exceptional density and direct fit.
2. **Replit (`replit`)** — explicit `Account Executive (Brazil)` plus a broad
   commercial organization.

This would add **2 requests/week**. Vanta should be the first Wave 2 candidate
only after its `Account Executive, LatAm` payload proves that the worker may be
based in Brazil/LATAM rather than merely own that sales territory. Deel,
Supabase, ClickHouse and incident.io remain a compact watchlist.

The conservative recommendation is intentionally smaller than the allowed
5–10: five tenants would cost +5 requests/week, while twenty would cost +20.
Adding uncertain tenants now would mostly buy geographic rejects and obscure
incremental value.

## How to measure a later pilot

The existing contribution model already supports the needed concepts. A later
implementation should report each tenant separately:

- incremental unique opportunities;
- incremental KEEP;
- incremental REVIEW;
- requests per relevant opportunity (`KEEP + REVIEW`);
- cross-source overlap.

After a bounded observation window, disable tenants with repeated zero relevant
yield or poor requests/relevant ratios. Do not auto-prioritize or change scoring.

## Exact next step

**Etapa 13H.6 — Ashby Wave 1 offline configuration and fixtures for ElevenLabs
and Replit.** Before registration, make one safe payload-shape validation per
tenant, confirm employer identity and exact worker-location semantics, then add
offline fixtures/tests. Do not add Vanta until the LATAM-territory ambiguity is
resolved.

## Wave 1 implementation decision — 13H.6

ElevenLabs and Replit are now operational configurations over the generic
Ashby components, not separate adapters. Their configured employer names are
safe because each is the company's own board; LatamCent remains a recruiting
publisher with no inferred client employer. All three tenants remain
`OBSERVATIONAL`.

The weekly increment is exactly two requests: one for ElevenLabs and one for
Replit, with no pagination, retries or extra queries. Direct company boards are
kept outside the global/recruiting contribution baseline until the reporting
model can represent direct monitoring separately. Vanta is the next candidate
only after location semantics are validated; all other researched tenants
remain unimplemented.

The API's `applyUrl` can differ from `jobUrl` and would matter to future
application automation. The current v8 model has no dedicated field, so adding
it requires an explicit schema proposal and migration. Wave 1 preserves
`jobUrl`, documents this limitation, and does not change schema.
