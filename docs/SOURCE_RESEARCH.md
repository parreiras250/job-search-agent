# Source Research Catalog

Research snapshot: 2026-08-16. This catalog is versioned evidence, not an
implementation allow-list. No endpoint was called while producing it; research
used provider documentation/pages only.

## Evidence and scoring rules

- **VERIFIED**: the linked official provider source directly supports the claim.
- **LIKELY**: official evidence exists, but a key operational detail still needs
  a controlled verification (for example read authentication or terms).
- **UNKNOWN**: not verified in this stage; never assume public/free access.
- **RESTRICTED**: official access is partner-only, login-bound, or unsuitable
  for a zero-cost public search integration.

Priority combines expected incremental relevant coverage, LATAM fit, structured
quality, effort, setup/cost and ToS risk. “Free” below refers to reading jobs,
not employer posting fees. `UNKNOWN` cost means it must be checked before work.

## Verified evidence

- [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html):
  published job GET endpoints are public/no-auth; data is board-token scoped.
- [Lever Postings API](https://github.com/lever/postings-api): published postings
  are site-scoped, paginated, queryable and include stable IDs, description,
  apply URL, workplace type and optional salary.
- [Ashby Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api):
  currently published jobs are job-board-name scoped; compensation can be
  requested optionally.
- [Workable public jobs endpoint](https://workable.readme.io/reference/jobs-1):
  returns public jobs for an account/subdomain. Authentication and usage terms
  for an unrelated read-only consumer still need confirmation.
- [We Work Remotely RSS](https://weworkremotely.com/remote-job-rss-feed): public
  all-jobs and category RSS, including Sales and Marketing; link attribution is
  requested.
- [Jobicy API/RSS](https://jobicy.com/jobs-rss-feed): public JSON API with
  count/geo/industry/tag filters, documented fields, fair-use frequency and
  distribution restrictions.
- [Remotive Public API](https://remotive.com/remote-jobs/api): public feed is for
  redistributing jobs, requires link-back/source attribution, is delayed, and a
  separate private paid API exists.
- [Arbeitnow Job Board API](https://www.arbeitnow.com/blog/job-board-api): free,
  no-key API with remote flag; coverage is described primarily as European and
  a custom private API is paid.
- [SmartRecruiters Posting API](https://developers.smartrecruiters.com/docs/endpoints):
  tenant/company scoped active postings with query, pagination, location and
  stable posting identifiers. Official pages differ on API-key wording, so
  anonymous operational access requires confirmation.
- [Recruitee Careers Site API](https://docs.recruitee.com/reference/intro-to-careers-site-api):
  company careers-site scoped and documented as no-auth for viewing offers.
- [Teamtailor API](https://docs.teamtailor.com/): structured jobs exist, but an
  API key is required even for the public-data scope.
- [Personio open positions](https://developer.personio.de/docs/retrieving-open-job-positions):
  company-scoped XML of open postings; current header/auth expectations should
  be verified before prioritizing.
- [LinkedIn Talent APIs](https://learn.microsoft.com/en-us/linkedin/talent/apply-connect/create-apply-connect-jobs):
  job-posting access is restricted to approved partners and is for publishing/
  managing customer jobs, not public job search.
- [Indeed Job Sync API](https://docs.indeed.com/job-sync-api/integrate-with-job-sync-api):
  requires a partner agreement/onboarding and manages jobs sent by ATS partners;
  it is not a public search API.
- [Glassdoor Jobs API](https://www.glassdoor.com/developer/jobsApiActions.htm):
  additional job APIs are available to API partners and attribution is required.
- [Google JobPosting documentation](https://developers.google.com/search/docs/appearance/structured-data/job-posting):
  documents how publishers make pages eligible for Google Search; it does not
  provide a public Google Jobs search feed for this project.

## Current sources

| Source | Category / scope | Access, auth, cost | LATAM / sales fit | Data, reliability, attribution | Complexity | Priority | Status |
|---|---|---|---|---|---|---|---|
| [Jobicy](https://jobicy.com/jobs-rss-feed) | Remote global board | Public JSON/RSS; no auth documented; read free under fair use | Explicit LATAM/Brazil geo and seller/category filters; high | Stable ID, description, date, optional salary; delayed feed; distribution/frequency rules | Low; already implemented | P0 baseline | VERIFIED |
| [Remotive](https://remotive.com/remote-jobs/api) | Remote global board/aggregator | Public API/RSS; public read free; private API paid | Remote sales category; location varies; medium/high | Description/date/URL; mandatory attribution/link-back; public jobs delayed | Low; already implemented | P0 baseline | VERIFIED |

## ATS and tenant-scoped company boards

| Source | Access method / scope | Public API, auth, cost | Useful fields / lifecycle | LATAM & sales potential | Complexity / concern | Priority | Status |
|---|---|---|---|---|---|---|---|
| [Greenhouse](https://developers.greenhouse.io/job-board.html) | JSON Job Board API; board token | GET no auth; zero-cost public reads | Published jobs, stable IDs, details; direct tenant snapshot is authoritative | High for curated US SaaS companies | Company Registry-backed; one request per tenant, default safety cap 25 | P0 | IMPLEMENTED DIRECT ATS + COMPANY REGISTRY |
| [Lever](https://github.com/lever/postings-api) | JSON Postings API; site + global/EU region | Public published postings; GET key not documented | Pagination, filters, stable ID, descriptions, apply URL, remote type, optional salary; authoritative candidate | High | Low/medium; tenant and region management | P0 | VERIFIED |
| [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api) | JSON postings; job board name | Public endpoint documented; no auth shown | Published jobs, locations, apply URL and optional compensation; authoritative candidate | High for startups/SaaS | Low/medium; new adapter + tenant registry | P0 | VERIFIED |
| [Workable](https://workable.readme.io/reference/jobs-1) | Public jobs by account/subdomain | Public-job endpoint exists; auth/terms/free read need confirmation | Structured account jobs; authority likely only after completeness verified | High for curated tech companies | Medium; verify access first | P1 | LIKELY |
| [SmartRecruiters](https://developers.smartrecruiters.com/docs/endpoints) | Posting API by company identifier | Public postings documented; official auth wording is inconsistent | Query, location, pagination, stable IDs; authoritative if complete | Medium/high | Medium; confirm anonymous/key access | P1 | LIKELY |
| [Recruitee](https://docs.recruitee.com/reference/intro-to-careers-site-api) | Careers Site API by company subdomain | Viewing jobs documented no-auth | Offers and career/apply URLs; tenant snapshot candidate | Medium | Medium; validate fields/pagination/terms | P1 | VERIFIED |
| [Personio](https://developer.personio.de/docs/retrieving-open-job-positions) | Company XML feed | Open-position XML documented; headers/access details need a pilot | ID, office, department, title, description; authoritative if full | Low/medium; more Europe-heavy hypothesis to measure | Medium; XML and access verification | P1 | LIKELY |
| [Teamtailor](https://docs.teamtailor.com/) | Tenant API | API token required; obtaining keys for unrelated companies is not viable | Rich jobs/relations and career URLs | Medium | High setup burden per company | DEFER | VERIFIED |
| Breezy HR | Tenant/career board | Public structured read not verified; auth/cost unknown | Unknown | Unknown | Research official docs/terms | P2 research | UNKNOWN |
| Comeet | Tenant/career board | Public structured read not verified; auth/cost unknown | Unknown | Unknown | Research official docs/terms | P2 research | UNKNOWN |
| Workday | Tenant career board | No official public job-search API verified here | Unknown completeness/IDs | Potentially high company coverage | High tenant URL/pagination variability; ToS review | DEFER | UNKNOWN |
| Jobvite | Tenant/career board | Public read method/auth/cost not verified | Unknown | Medium | Research required | DEFER | UNKNOWN |
| iCIMS | Tenant/career board | Public read method/auth/cost not verified | Unknown | Medium | Research required | DEFER | UNKNOWN |

## Remote and global boards

| Source | Access / cost | Scope and likely fit | Reliability / attribution / ToS | Complexity | Priority | Status |
|---|---|---|---|---|---|---|
| [We Work Remotely](https://weworkremotely.com/remote-job-rss-feed) | Official public RSS; link attribution requested | Global remote; Sales and Marketing feed; strong role fit, geography evaluated per job | Official category feed integrated with one GET; WWR URL and attribution preserved | Low RSS adapter, implemented in 13C | P0 | IMPLEMENTED / VERIFIED |
| [Arbeitnow](https://www.arbeitnow.com/blog/job-board-api) | Free no-key API; custom private API paid | Global endpoint but Europe-oriented coverage; remote flag; LATAM incremental gain uncertain | Official API; aggregated ATS data | Low | P1 pilot | VERIFIED |
| [RemoteOK](https://remoteok.com/api) | Official public JSON feed; no auth observed | Remote/global; title, company, description, location, tags, salary, date, stable ID and RemoteOK URL | First object is legal/update metadata and is excluded deterministically; feed requires RemoteOK mention and link-back | Low; one GET implemented in 13G.3 | P0 | IMPLEMENTED / VERIFIED |
| [Himalayas](https://himalayas.app/docs/remote-jobs-api) | Official free public JSON search API; no auth; attribution required | Remote/global; structured country/worldwide restrictions; LATAM incremental gain still to measure | One `sales` search page per operational run; salary, dates, location and timezone restrictions preserved | Low; implemented in 13G.1 | P0 | IMPLEMENTED / VERIFIED |
| [Working Nomads](https://www.workingnomads.com/) | Structured public access not verified | Remote/global; sales category likely but not verified | Verify feed/API, attribution and terms | Unknown | P2 research | UNKNOWN |
| [Dynamite Jobs](https://dynamitejobs.com/) | Structured public access not verified | Remote roles; sales relevance plausible, unmeasured | Verify official access and terms | Unknown | P2 research | UNKNOWN |
| [Remote.co](https://remote.co/) | Structured public access not verified | Remote/global; relevance unmeasured | Verify official access and terms | Unknown | DEFER | UNKNOWN |
| [NoDesk](https://nodesk.co/) | Structured public access not verified | Remote/global; relevance unmeasured | Verify official feed/API and terms | Unknown | DEFER | UNKNOWN |
| [Jobgether](https://jobgether.com/) | Structured public access not verified | Remote/global aggregator hypothesis | Verify access, provenance and terms | Unknown | DEFER | UNKNOWN |
| [Remote Rocketship](https://www.remoterocketship.com/) | Structured public access not verified | Remote/global; relevance unmeasured | Verify access, cost and terms | Unknown | DEFER | UNKNOWN |

## Aggregators and APIs

All entries below require official API/pricing/terms verification before design.
API presence in an old directory or third-party marketplace is not sufficient.

| Source | Access/auth/cost | Fit and concern | Priority | Status |
|---|---|---|---|---|
| [Adzuna](https://developer.adzuna.com/) | API is plausible; current key, free-tier, credit-card and redistribution terms not verified | Broad coverage; duplication and LATAM quality must be measured | P2 research | UNKNOWN |
| [Jooble](https://jooble.org/api/about) | API/key is plausible; current zero-cost availability and terms not verified | Broad aggregator; likely high duplication | P2 research | UNKNOWN |
| [Careerjet](https://www.careerjet.com/partners/api/) | API/partner access and current cost not verified | Broad aggregator; attribution and relevance unknown | DEFER | UNKNOWN |
| [The Muse](https://www.themuse.com/developers/api/v2) | API/key/free-tier status not verified from current official evidence | Tech/company content; LATAM coverage unknown | P2 research | UNKNOWN |
| [Findwork](https://findwork.dev/developers/) | API/key/cost not verified | Tech-heavy; sales relevance may be low | DEFER | UNKNOWN |

## LATAM and Brazil

This is the largest evidence gap. These names are research leads, not approved
automation targets. None received a `VERIFIED` public zero-cost read API in this
audit.

| Source | Likely market / relevance | Public API/feed, auth, cost, ToS | Priority | Status |
|---|---|---|---|---|
| [Torre](https://torre.ai/) | LATAM/global talent; potentially strong | Not verified | P1 research | UNKNOWN |
| [Get on Board](https://www.getonbrd.com/) | LATAM tech; potentially strong for startups/SaaS | Not verified | P1 research | UNKNOWN |
| [Gupy](https://www.gupy.io/) | Brazil ATS/board; high geographic relevance | Public search API not verified | P1 research | UNKNOWN |
| [Vagas](https://www.vagas.com.br/) | Brazil board; broad roles | Not verified | P2 research | UNKNOWN |
| [Catho](https://www.catho.com.br/) | Brazil board | Subscription/access/automation terms not verified | DEFER | UNKNOWN |
| [InfoJobs](https://www.infojobs.com.br/) | Brazil board | Not verified | DEFER | UNKNOWN |
| [Workana](https://www.workana.com/) | LATAM freelance marketplace; employment fit differs | API/access not verified | DEFER | UNKNOWN |
| [Revelo](https://www.revelo.com/) | LATAM talent platform, likely tech-heavy | Public jobs feed not verified | DEFER | UNKNOWN |
| [GeekHunter](https://www.geekhunter.com.br/) | Brazil tech talent; low direct sales hypothesis | Public feed not verified | DEFER | UNKNOWN |
| [HireLATAM](https://hirelatam.com/) | LATAM remote hiring; role relevance plausible | Public structured access not verified | P2 research | UNKNOWN |
| [Somewhere](https://somewhere.com/) | Remote talent/LATAM relevance plausible | Public structured access not verified | P2 research | UNKNOWN |
| [Near](https://www.hirewithnear.com/) | LATAM hiring; company/recruiting service | Public jobs API/feed not verified | DEFER | UNKNOWN |
| [LatamCent](https://latamcent.com/) | LATAM remote hiring; sales relevance plausible | Public structured access not verified | P2 research | UNKNOWN |
| [Virtual Latinos](https://www.virtuallatinos.com/) | LATAM remote roles; contractor/service model | Public feed/access not verified | DEFER | UNKNOWN |

## Startup and technology ecosystems

| Source | Coverage hypothesis | Access/auth/cost/ToS | Priority | Status |
|---|---|---|---|---|
| [Wellfound](https://wellfound.com/jobs) | High startup/SaaS and US-company potential | Public structured API/feed not verified; login/terms review needed | P1 research | UNKNOWN |
| [YC Work at a Startup](https://www.workatastartup.com/jobs) | High-quality startup corpus; geography varies | Public automation method and login requirements not verified | P1 research | UNKNOWN |
| [Techstars Jobs](https://jobs.techstars.com/) | Startup ecosystem; potential incremental coverage | Underlying access method/terms not verified | P2 research | UNKNOWN |
| [Built In](https://builtin.com/jobs) | US tech/startup; sales relevance likely | Public API/feed and automation terms not verified | P2 research | UNKNOWN |
| [Welcome to the Jungle](https://www.welcometothejungle.com/) | Tech/startup, strong Europe presence hypothesis | Public API/feed not verified | DEFER | UNKNOWN |

## Sales-specific communities and boards

No candidate below has verified public zero-cost structured access in this audit.
Human/community access must not be converted into login automation.

| Source | Sales relevance | Access/auth/cost/automation concern | Priority | Status |
|---|---|---|---|---|
| [RepVue](https://www.repvue.com/jobs) | Very high | Public API/feed not verified; account/subscription features possible | P1 research | UNKNOWN |
| [Bravado](https://bravado.co/jobs) | Very high | Public structured access and terms not verified | P1 research | UNKNOWN |
| [RevGenius](https://www.revgenius.com/) | High community relevance | Job-board/feed availability and login terms not verified | P2 research | UNKNOWN |
| [Pavilion](https://www.joinpavilion.com/) | High community relevance | Membership/subscription and public job access not verified | DEFER | UNKNOWN |
| Other sales boards | Potentially high | Add only with official evidence, zero-cost read access and clear terms | Research queue | UNKNOWN |

## Restricted and special sources

| Source | Official access finding | Why not implement | Priority | Status |
|---|---|---|---|---|
| [LinkedIn](https://learn.microsoft.com/en-us/linkedin/talent/apply-connect/create-apply-connect-jobs) | Talent job-posting APIs require approved partner status/agreement and manage customer postings | No public search API; no login automation, scraping, Selenium or CAPTCHA bypass | BLOCKED/RESTRICTED | RESTRICTED |
| [Indeed](https://docs.indeed.com/job-sync-api/integrate-with-job-sync-api) | Job Sync requires partner agreement, onboarding and OAuth credentials; manages partner jobs | Not a public search feed; no scraping or login automation | BLOCKED/RESTRICTED | RESTRICTED |
| [Glassdoor](https://www.glassdoor.com/developer/jobsApiActions.htm) | Official page says additional Jobs APIs are for API partners; attribution required | Public zero-cost general search access is not established | BLOCKED/RESTRICTED | RESTRICTED |
| [Google Jobs](https://developers.google.com/search/docs/appearance/structured-data/job-posting) | Publisher structured-data/indexing guidance, not a job-search API | Search-result scraping is not an acceptable substitute | BLOCKED/RESTRICTED | RESTRICTED |

## Prioritization matrix

| Tier | Candidates | Rationale / gate |
|---|---|---|
| **P0** | Jobicy, Remotive, We Work Remotely RSS, Himalayas, RemoteOK; framework support for Greenhouse, Lever, Ashby | Strong official evidence, structured data, zero-cost public read path documented or already implemented, high expected remote/startup coverage. |
| **P1** | Arbeitnow pilot; Workable, SmartRecruiters, Recruitee, Personio verification; focused research on Torre, Get on Board, Gupy, Wellfound, YC, RepVue, Bravado | Promising coverage or geography, but access terms, auth, completeness or actual incremental gain remains a gate. |
| **P2** | Working Nomads, Dynamite Jobs, Adzuna, Jooble, The Muse, Techstars, Built In, HireLATAM, Somewhere, LatamCent, RevGenius | Research queue; do not schedule until official access/cost/attribution is verified. |
| **DEFER** | Teamtailor, Breezy, Comeet, Workday, Jobvite, iCIMS, Remote.co, NoDesk, Jobgether, Remote Rocketship, Careerjet, Findwork, Vagas, Catho, InfoJobs, Workana, Revelo, GeekHunter, Near, Virtual Latinos, Welcome to the Jungle, Pavilion | Higher setup/uncertainty, weaker expected fit, or no verified public method. Re-evaluate after P0/P1 metrics. |
| **BLOCKED / RESTRICTED** | LinkedIn, Indeed, Glassdoor, Google Jobs | Partner/publisher-only or no public search access. Never use brittle/prohibited scraping or login automation. |

## Zero-cost gates

Before any candidate moves to implementation, record answers to all of these:

1. Is job reading free without a paid subscription or credit card?
2. Is access public, or can Daniel legitimately obtain required credentials?
3. Are request limits adequate for a weekly local workflow?
4. Are local storage, analysis and link display compatible with terms?
5. Is attribution/link-back implemented exactly as required?
6. Is the source useful without a paid/private tier?

Known flags: Remotive explicitly offers a separate paid private API, but its
public attributed feed remains usable under its stated rules; Arbeitnow offers a
paid custom API in addition to the free endpoint; Teamtailor requires a tenant
API key; LinkedIn/Indeed/Glassdoor require partner-style access for the relevant
official APIs. None may become a required paid dependency.

## Research queue

For each `UNKNOWN` P1/P2 source, the next research pass should capture an
official documentation/terms URL, exact read endpoint or feed, authentication,
current pricing/free limits, attribution, pagination, stable IDs, direct-apply
URL and robots/automation restrictions. If those cannot be established, keep it
`UNKNOWN` or move it to `RESTRICTED`; do not “test by scraping.”

## Etapa 13H.1 — LATAM source intelligence

Research snapshot: 2026-08-17. This pass used provider documentation, help
centers, official job/candidate pages and official provider repositories. It did
not call a jobs endpoint, inspect private frontend traffic or execute discovery.

The implementation labels below are independent from evidence status:

- `IMPLEMENT_NOW`: enough official evidence exists to build an offline-tested,
  conservative integration using the documented public contract.
- `NEEDS_ACCESS`: Daniel or the source owner must legitimately authorize access.
- `NEEDS_TECHNICAL_VALIDATION`: the product is promising, but its tool contract,
  limits, completeness or unattended behavior is not sufficiently documented.
- `DO_NOT_IMPLEMENT`: no acceptable automated path or insufficient expected
  value for the current agent.

### Decision matrix

| Priority | Source | Evidence | Access decision | Daniel Job Agent value | Recommendation |
|---|---|---|---|---|---|
| **P0** | [Get on Board](https://www.getonbrd.com/user-manual/get-on-board-s-api) | VERIFIED public API; limits partially verified | No auth for public facet; private API is unrelated and paid | LATAM tech board, public job search, structured remote/category/location and salary-rich postings; likely unique regional coverage | **IMPLEMENT_NOW** as 13H.2, with conservative pagination and attribution |
| **P1** | [Gupy candidate MCP](https://candidatos.gupy.io/ia-para-pessoas-candidatas) | VERIFIED product; tool schema/limits not published in the reviewed page | Free candidate MCP; unattended use and result completeness need validation | Very high Brazil coverage; likely broad role mix, but incremental sales quality unknown | **NEEDS_TECHNICAL_VALIDATION**; do not use employer API |
| **P1** | [Torre API for professionals](https://torre.ai/apiforprofessionals) | ACCESS_REQUIRED | Private beta; request access | Strong LATAM/remote corpus, structured location/timezone/salary potential | **NEEDS_ACCESS** |
| **P1** | [HireLATAM jobs](https://hirelatam.com/jobs/) | PARTIALLY_VERIFIED | Public candidate page uses Recruiterflow; official API key is workspace-bound | Excellent LATAM + US-company fit; explicit SDR, AE, sales ops and remote US hours | **NEEDS_ACCESS** from HireLATAM/Recruiterflow workspace owner; never bypass auth |
| **P1** | [Somewhere jobs](https://jobs.somewhere.com/) | PARTIALLY_VERIFIED | Public board is hosted through RecruitCRM; no official anonymous feed verified | Excellent US-company, full-time remote and sales-role fit; geography also includes non-LATAM pools | **NEEDS_ACCESS** or an owner-approved feed |
| **P1** | [LatamCent careers](https://latamcent.com/careers/) | PARTIALLY_VERIFIED | Public careers UI, but no official API/feed verified | Exceptional B2B SaaS, AE, SDR, CSM, RevOps and US-company focus | **NEEDS_TECHNICAL_VALIDATION**; no HTML scraping |
| **P1** | [Near jobs](https://www.hirewithnear.com/find-a-job) | PARTIALLY_VERIFIED | Public listings, no official API/feed verified | LATAM-only candidates, US employers, sales/CS/ops and Brazil explicitly supported | **NEEDS_ACCESS** or official feed confirmation |
| **P2** | [Interfell](https://www.interfell.com/profesionales) | PARTIALLY_VERIFIED | Candidate registration precedes platform access; no public feed verified | LATAM remote, startups/fintech/software and some tech-commercial roles; more tech-heavy | **DO_NOT_IMPLEMENT** until an official public feed exists |
| **P2** | [Startup.jobs](https://startup.jobs/api) | VERIFIED structured API/RSS/MCP | Public API/RSS advertised; attribution required | Strong startup corpus and sales feeds, but not LATAM-specific and likely overlaps global boards | **NEEDS_TECHNICAL_VALIDATION** after LATAM wave |
| **P2** | [YC Jobs](https://www.ycombinator.com/jobs) | VERIFIED public candidate product | No official public job-search API/feed verified | Excellent B2B/startup and sales quality; LATAM eligibility is sparse and must be evaluated per job | **DO_NOT_IMPLEMENT** without an official automation contract |
| **DEFER** | [GeekHunter](https://www.geekhunter.com.br/candidates/signup) | VERIFIED applicant platform; no public API/feed verified | Candidate account/profile workflow | Strong Brazil/tech, but present positioning and matching are technology-heavy; low GTM leverage | **DO_NOT_IMPLEMENT** |
| **DEFER** | [Revelo](https://careers.revelo.com/) | VERIFIED applicant platform | Profile/matching workflow; no public feed verified | LATAM and US companies, but explicitly senior software/AI focused | **DO_NOT_IMPLEMENT** for a sales agent |
| **DEFER** | [Workana](https://www.workana.com/work) | PARTIALLY_VERIFIED | Public marketplace pages; no acceptable official feed found | Freelance/project model and full-time developer program do not match core AE/CSM search | **DO_NOT_IMPLEMENT** |
| **DEFER** | [Virtual Latinos](https://join.virtuallatinos.com/how-it-works/) | RESTRICTED applicant-only | Approval is required before access to the exclusive job portal | US/Canada clients and sales/VA roles, but closed candidate portal prevents unattended public discovery | **DO_NOT_IMPLEMENT** |
| **BLOCKED** | [Wellfound](https://wellfound.com/terms) | RESTRICTED | Candidate account product; no public API/feed; terms constrain automated systems | High startup relevance, uncertain LATAM availability | **DO_NOT_IMPLEMENT** |

`HireInCloud` (and similarly named services) was not added: this pass did not
verify a distinct, credible official board with an acceptable access contract.
That avoids turning a search lead into an invented source.

### Get on Board — P0 / IMPLEMENT_NOW

Official evidence is unusually strong. Get on Board documents a public and a
private API facet. The public facet needs no setup or authentication and exposes
published jobs, companies, categories, technologies, locations and free-text
job search. The provider explicitly lists building a custom job board and
studying public job-market data as supported uses. Its
[official Ruby client](https://github.com/getonbrd/getonbrd-ruby) demonstrates
`page`, `per_page`, expandable tags, category jobs, free-text search, remote
status/modality and stable job resources. The private API and subscription are
not needed.

Public job pages show stable `GETONBRD Job ID`, company, title, description,
conditions, technologies, remote policy, geographic eligibility and, when
provided, compensation. The public API should therefore be modeled as one
`GLOBAL_BOARD` with LATAM coverage, observational lifecycle and the original
Get on Board URL. The provider's privacy notice says affiliated third-party
display must disclose Get on Board as the source, so attribution/link-back is a
hard capability.

Remaining uncertainty is operational rather than architectural: the reviewed
official material did not state a numeric public rate limit, retention policy or
complete current field schema. 13H.2 should use one narrow query/page initially,
no detail fan-out, a descriptive User-Agent, conservative request budget and
offline fixtures. Pagination should be bounded even though it is supported.
Salary must be preserved without currency conversion; location and remote
modality must remain structured; missing fields remain UNKNOWN. This is a
zero-paid-dependency integration under the officially documented public facet.

### Gupy — P1 / NEEDS_TECHNICAL_VALIDATION

Two products must not be conflated:

1. The [Gupy R&S REST API](https://developers.gupy.io/v2.0/reference/authentication)
   is an employer/customer integration. `GET /api/v1/jobs` is paginated, but it
   requires a Bearer token created by a master/admin of a Premium or Enterprise
   customer account. The token is company-bound and may expose management data.
   It is not a credential for searching the public Gupy universe and is
   **BLOCKED** for this project.
2. The official [Gupy candidate MCP](https://candidatos.gupy.io/ia-para-pessoas-candidatas)
   is free, uses the remote endpoint
   `https://candidates.mcp.api.gupy.io/mcp`, and explicitly searches jobs from
   Gupy's candidate portal. The setup examples target Gemini CLI, Claude and
   Cursor. The reviewed page does not publish a stable tool/result schema,
   pagination/completeness semantics, numeric rate limits, service-level terms
   for unattended weekly execution or a plain Python REST contract.

The MCP should not be disguised as `HttpTransport.get()`. MCP involves tool
discovery and invocation, possibly conversational/auth state, while a REST feed
is a deterministic pull. The safest future design is an external MCP ingestion
boundary that validates tool results into `RawJobRecord` batches and then uses
the normal adapter/pipeline. Only after its schema and unattended authorization
are validated should a protocol-neutral execution definition join the registry.
It must remain observational, and no candidate profile or application action
should be automated.

A fallback is Company Registry metadata for known Gupy tenant career pages.
That would be tenant-scoped and may have better lifecycle semantics, but no
official anonymous tenant feed was verified here. Do not scrape career pages or
reuse the employer Bearer API.

### HireLATAM — P1 / NEEDS_ACCESS

HireLATAM's official candidate page says every listed role is remote, requires
the candidate to be based in LATAM, uses English interviews and connects to US
companies. Its role catalog explicitly includes SDR/BDR, Account Executive,
Account Manager, sales support, CRM support and customer support. This is a
high-value `RECRUITING_BOARD`, not a company ATS board.

The page's job widget and talent-pool links are hosted by Recruiterflow.
[Recruiterflow's official help](https://help.recruiterflow.com/en/articles/3671870-build-a-custom-careers-page-with-the-recruiterflow-api)
says its public careers API returns open-job title, description, location,
employment type and application URL, but the API key is issued for and tied to
the agency workspace. It is not a general candidate key. A generic Recruiterflow
adapter could later serve multiple recruiting agencies only when each workspace
owner explicitly authorizes a server-side key. Daniel must not request or infer
HireLATAM's key, and the embedded public UI is not permission to reverse engineer
or bypass that authentication.

### Torre — P1 / NEEDS_ACCESS

Torre officially advertises both endpoints and an MCP server for professionals,
including job discovery, job-database queries and match notifications. However,
the professional API is in private beta and explicitly requires an access
request. Public pricing, auth flow, stable schemas and rate limits were not
published in the reviewed page. Classification: `ACCESS_REQUEST_REQUIRED`, not
READY.

If access is granted, validate the official endpoint/MCP contract and prefer a
protocol-neutral ingestion layer like the Gupy proposal. Do not design around
frontend calls. Torre's rich salary, remote, country and timezone presentation
suggests strong normalized-field potential, but that is a value hypothesis until
the authorized API schema is available.

### Somewhere — P1 / NEEDS_ACCESS

Somewhere's official candidate board describes full-time remote roles at US and
European companies, and its official role catalog includes AE, SDR, Sales
Manager, Sales Rep and customer-facing positions. It recruits across LATAM,
South Africa and the Philippines, so eligibility must still be evaluated per
job.

The candidate job-board link is hosted through RecruitCRM. RecruitCRM documents
API-powered careers pages for its customers, but this pass found no official
anonymous, reusable jobs feed for third-party consumers. Treat it as a valuable
`RECRUITING_BOARD` requiring provider/agency authorization, not as a frontend
endpoint to copy. No integration is recommended without an official feed or an
owner-approved credential.

### GeekHunter — DEFER / DO_NOT_IMPLEMENT

GeekHunter is now an applicant/profile and matching platform with a job mural.
Its official pages describe Brazil plus international opportunities and
multi-currency compensation, but candidate registration/profile approval is a
core part of access and no official public jobs API, feed or RSS was found. The
current employer positioning and candidate help remain strongly technology
oriented; sales/GTM incremental value is therefore lower than the agency boards.
Do not automate login or the job mural.

### Other LATAM candidates

- **LatamCent:** strongest content fit in the group: it focuses on US B2B SaaS
  and explicitly recruits AE, SDR, Account Manager, RevOps, CSM, Solutions
  Engineer and Sales Enablement. Its public careers page is real, but no official
  structured access was verified. Keep P1 and ask for a candidate jobs feed.
- **Near:** official candidate pages cover LATAM-only placements with US
  companies across sales, CS, finance, tech and operations. No official feed was
  found. High human value, no safe automation path yet.
- **Interfell:** verified remote LATAM platform for startups, fintech and
  software companies, with tech-commercial profiles, but platform registration
  and a technology-heavy corpus reduce immediate leverage.
- **Workana:** the public corpus is primarily freelance projects; its dedicated
  full-time offering is aimed at developers. That is a poor match for the core
  sales agent even before access questions.
- **Revelo:** excellent LATAM-to-US model but explicitly optimized for senior
  software engineers and AI work, so it is not a GTM source candidate.
- **Virtual Latinos:** US/Canada remote roles include sales and business
  development, but job access follows application, English testing, approval
  and login. It is applicant-only and unsuitable for discovery automation.
- **YC Jobs:** public pages expose startup roles and sales categories, but no
  official read API/feed was verified. Do not scrape them. Company Registry ATS
  coverage may capture part of the useful corpus more safely.
- **Startup.jobs:** a credible non-LATAM discovery from this pass. Its official
  API page offers API, filtered RSS and MCP with link attribution. It belongs in
  a later global-source comparison, not ahead of Get on Board or access work on
  LATAM-specific recruiting boards.

### Proposed `RECRUITING_BOARD` source type

Recruiting agencies publish one cross-client corpus, so `TENANT_BOARD` is wrong:
the tenant is the agency, but each job belongs to a client and the agency may
remain the application authority. `GLOBAL_BOARD` is mechanically workable but
hides curation, client confidentiality and weaker closure authority.

Adding `RECRUITING_BOARD` later would improve reporting, source-quality analysis
and lifecycle policy. Its downside is another enum dimension when scope and
ownership could instead be independent capabilities. Recommendation: do not
change the enum in 13H.1. First integrate Get on Board as `GLOBAL_BOARD`; if an
authorized agency feed becomes available, decide whether to add the type or a
`publisher_model=RECRUITING_AGENCY` capability based on the real contract.

### Manual access actions

1. Submit Torre's official professional API private-beta access request. Do not
   pay or agree to employer/company API access for this use case.
2. Connect/test Gupy candidate MCP manually in a supported client and record
   tool names, schemas, pagination, authorization persistence and limits. Do not
   provide candidate documents or permit application actions during validation.
3. Ask HireLATAM, Somewhere, LatamCent and Near whether they offer an official
   candidate-facing RSS/API and permit low-frequency personal aggregation with
   attribution. Do not ask them to disclose workspace API keys.
4. No manual access action is required for Get on Board's public facet.

### Recommended Wave 1 order

1. **13H.2 — Get on Board public API.** Implement one conservative public jobs
   query/page, offline adapter fixtures, attribution and an opt-in manual demo.
2. **13H.3 — Gupy candidate MCP technical validation, not production enablement.**
   Capture the authorized tool contract and decide whether a protocol adapter is
   deterministic enough for weekly ingestion.
3. **13H.4 — Recruiting-board access pilot.** Use HireLATAM first if its owner
   provides an official feed/authorization; otherwise LatamCent, Near or
   Somewhere may take the slot. No access means no implementation.
4. **13H.5 — Torre authorized pilot**, only if private-beta access is granted.

The exact next implementation is therefore **13H.2 Get on Board**. It is the
only high-fit LATAM candidate in this pass with verified public, structured,
no-auth access explicitly intended for published-job search and third-party job
display.
