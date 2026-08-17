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
| [RemoteOK](https://remoteok.com/) | API/feed/auth/cost not verified in this audit | Remote/global and potentially sales relevant | Terms, attribution and automation need official verification | Unknown | P2 research | UNKNOWN |
| [Himalayas](https://himalayas.app/) | Structured public access not verified | Remote/global; likely useful, LATAM coverage unmeasured | Verify official API/feed and terms | Unknown | P2 research | UNKNOWN |
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
| **P0** | Jobicy, Remotive; framework support for Greenhouse, Lever, Ashby; We Work Remotely RSS | Strong official evidence, structured data, zero-cost public read path documented or already implemented, high expected remote/startup coverage. ATS execution waits for registry/provenance. |
| **P1** | Arbeitnow pilot; Workable, SmartRecruiters, Recruitee, Personio verification; focused research on Torre, Get on Board, Gupy, Wellfound, YC, RepVue, Bravado | Promising coverage or geography, but access terms, auth, completeness or actual incremental gain remains a gate. |
| **P2** | RemoteOK, Himalayas, Working Nomads, Dynamite Jobs, Adzuna, Jooble, The Muse, Techstars, Built In, HireLATAM, Somewhere, LatamCent, RevGenius | Research queue; do not schedule until official access/cost/attribution is verified. |
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
