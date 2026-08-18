# LATAM Recruiting Sources — access research (13H.3)

Research date: 2026-08-18. This is a product/access decision, not an
implementation specification. No job endpoint was bulk queried and no source,
model, enum or scoring rule was changed.

## Decision

| Source | Model | Candidate Fit | GTM Fit | Technical Access | Automation | Expected Value | Recommendation |
|---|---|---|---|---|---|---|---|
| [LatamCent](https://latamcent.com/careers/) | Recruiting agency / staffing partner focused on AI and B2B SaaS | VERY_HIGH | VERY_HIGH | **PUBLIC_ATS_ENDPOINT** — verified Ashby board `latamcent` and official public Job Postings API | Sustainable weekly one-request read; no auth; no scraping | **VERY_HIGH** | **IMPLEMENTED_OFFLINE** |
| [HireLATAM](https://hirelatam.com/jobs/) | Recruiting agency; candidates apply to individual jobs or join its pool | VERY_HIGH | HIGH | **OFFICIAL_ACCESS_REQUIRED** — verified Recruiterflow board; API key is workspace-bound and issued by Recruiterflow | Good only with written owner authorization and server-side key | **VERY_HIGH** if access is granted | **REQUEST_ACCESS** |
| [Near](https://www.hirewithnear.com/find-a-job) | Staffing and recruiting agency; direct applications followed by agency screening | VERY_HIGH | HIGH | **UNKNOWN** — public custom career portal, but no official reusable API/feed contract verified | Not approved for unattended use; ask Near for an official feed | **HIGH** | **REQUEST_ACCESS** |
| [Somewhere](https://jobs.somewhere.com/) | Global recruiting agency/talent network; individual applications and matching | HIGH | HIGH | **PARTNER_ACCESS_REQUIRED** — verified RecruitCRM application path; its API requires a Business plan and workspace token | Technically possible only with Somewhere/RecruitCRM authorization | **HIGH** | **MONITOR** pending owner-approved access |
| [Gupy candidate product](https://candidatos.gupy.io/ia-para-pessoas-candidatas) | Broad ATS/candidate marketplace | HIGH for Brazil, broad rather than GTM-specific | MEDIUM/UNKNOWN | Candidate MCP exists; unattended completeness and stable result contract remain unverified | Requires a separate MCP validation and may optimize volume rather than outcomes | **LOW** for the current roadmap | **DEFER** |

The concrete recommendation is **13H.4 — LatamCent official Ashby board
integration**. It combines the strongest role specialization with the only
verified, public, no-auth ATS contract among the four. This conclusion is about
expected application outcomes and sustainable access, not raw listing volume.

## 1. HireLATAM

### Product and market fit

HireLATAM explicitly describes itself as a LATAM staffing and recruiting agency
for US companies. Its candidate page says open roles are remote, require a
LATAM-based candidate and English interviews. Candidates can apply to a listed
role or join the talent pool. Its current product material explicitly names
SDRs, AEs, sales operations, appointment setters, sales assistants, CRM support
and customer support. This is a `RECRUITING_AGENCY`, not a general job board or
direct employer.

### Technical access

The official jobs page embeds a hosted
[Recruiterflow HireLATAM board](https://recruiterflow.com/hirelatam/jobs). The
[Recruiterflow careers API guide](https://help.recruiterflow.com/en/articles/3671870-build-a-custom-careers-page-with-the-recruiterflow-api)
confirms that its API can return open-job title, description, location,
employment type, application URL and other metadata. However, Recruiterflow
issues the key for a specific agency workspace after an owner/admin request and
requires it to remain server-side. The hosted public board does not grant Daniel
permission to obtain or reuse that credential.

No official anonymous Recruiterflow JSON/RSS/XML feed, MCP or reusable public
ATS endpoint was verified. Numeric public-API rate limits and attribution terms
were not stated in the reviewed guide. The stable path is therefore to ask
HireLATAM to authorize read-only use of its official careers API or provide an
owner-approved feed. Do not parse its widget or reverse engineer browser calls.

### Data quality

| Field | Status | Evidence |
|---|---|---|
| External job ID | UNKNOWN | likely API metadata, but not enumerated in the official guide |
| Title, description, location, employment type, application URL | VERIFIED | Recruiterflow careers API guide |
| Company | PARTIAL | agency boards may intentionally use confidential clients |
| Remote / LATAM eligibility | PARTIAL | guaranteed at board-policy level; per-job structured fields not verified |
| Salary, publication date, timezone | UNKNOWN | not promised by the reviewed API guide |

Expected value is **VERY_HIGH**, but access is the gate. Prefer a generic
Recruiterflow adapter only after legitimate workspace authorization; do not add
HireLATAM to Company Registry as if it were a direct employer.

## 2. Near

### Product and market fit

[Near's candidate page](https://www.hirewithnear.com/find-a-job) says it places
professionals exclusively from Latin America into full-time remote roles with
US companies. Candidates browse and apply to individual openings; Near screens
them and presents strong profiles to the hiring company. It explicitly lists
SDR, BDR, outbound sales, Account Executive, Account Manager and Sales Manager,
plus customer support, marketing and operations. Most roles require US-hours
overlap and professional English.

This is a staffing/recruiting agency. It is not merely a self-service board and
not a direct employer, although candidates work directly for the client after
placement.

### Technical access

Near exposes a public branded career portal at `jobs.hirewithnear.com`, with
search, categories, job pages and applications. The observable pages provide
stable job URLs, titles, categories, location, date, descriptions and sometimes
compensation. The reviewed official material did **not** identify a supported
public API, RSS/XML/JSON feed, MCP, webhook or reusable ATS endpoint. It also did
not officially identify the underlying portal vendor. Consequently the ATS is
recorded as **UNKNOWN**, even though third-party traces suggest historical ATS
products.

[Near's terms](https://www.hirewithnear.com/terms-and-conditions) describe a
candidate/employer registration and job-alert service but do not establish a
third-party syndication API. A public webpage is not itself an automation
contract. Weekly unattended ingestion should wait for written confirmation or
an official feed; no HTML or private frontend endpoint should be used.

### Data quality

| Field | Status | Evidence |
|---|---|---|
| Stable job URL, title, description, location, category/date | VERIFIED | public career pages |
| Company | PARTIAL | many listings use “Confidential Client” |
| Remote / LATAM eligibility | VERIFIED at publisher level | Near explicitly limits placements to LATAM and remote US-company roles |
| Salary / employment type | PARTIAL | present in some public listings, not guaranteed |
| External ID | PARTIAL | stable IDs appear in job URLs; no official API contract |
| Timezone restriction | PARTIAL | US-hours overlap is common policy; per-job structured field unverified |

Expected value is **HIGH** and likely outcome quality is strong. Recommendation:
**REQUEST_ACCESS** for a read-only official jobs feed/API and its unattended-use
terms. Without that, remain manual.

## 3. Somewhere

### Product and market fit

[Somewhere's candidate site](https://jobs.somewhere.com/) identifies it as a
recruiting agency matching global professionals to full-time remote roles at US
and European companies. Candidates apply to listed roles and may enter the
agency's matching process. It recruits in LATAM, the Philippines, South Africa
and other regions, so LATAM/Brazil eligibility must still be evaluated per job.

Official role pages cover Account Executive, sales representative, sales
manager, lead qualification, client relations and customer support. GTM fit is
high, but the corpus is global rather than LATAM-exclusive.

### Technical access

The candidate site's Apply route points to RecruitCRM, confirming the recruiting
system in current use. [Recruit CRM's official API documentation](https://docs.recruitcrm.io/)
documents REST/JSON job access, Bearer-token authentication, a Business-plan
requirement and a limit of 60 requests per minute. Tokens are privileged
workspace credentials. Its managed-site material also describes an API-powered
careers page, but no anonymous third-party feed was verified.

Therefore the classification is **PARTNER_ACCESS_REQUIRED**, not public API.
Somewhere would need to authorize a read-only token/feed and clarify
redistribution/attribution. Do not copy a widget request or automate candidate
login. Its service agreement also treats client/search information as
confidential, reinforcing the need to use only explicitly public jobs and an
owner-approved contract.

### Data quality

| Field | Status | Evidence |
|---|---|---|
| Job ID/title/company/location/description/status | PARTIAL | RecruitCRM supports job objects, but Somewhere's authorized schema was not inspected |
| Application URL | VERIFIED | public candidate site routes applications to RecruitCRM |
| Remote/employment/salary/date/timezone | UNKNOWN/PARTIAL | visible selectively; no authorized field contract verified |
| LATAM eligibility | UNKNOWN per job | Somewhere recruits across several world regions |

Expected value is **HIGH**, but likely overlap and global eligibility review are
higher than HireLATAM/Near/LatamCent. Recommendation: **MONITOR** and request
partner access only after the higher-priority paths.

## 4. LatamCent

### Product and market fit

[LatamCent careers](https://latamcent.com/careers/) describes a nearshore
recruiting/staffing partner for US AI and B2B SaaS companies. Its stated GTM
catalog includes Account Executive, SDR, Account Manager, Revenue Operations,
Customer Success, Solutions Engineer, GTM Architect and Sales Enablement. Its
[candidate outcomes page](https://latamcent.com/latam-talent/) describes LATAM
professionals placed into long-term roles at US startups. Candidates apply to
individual roles; recruiting staff also maintain a talent pool.

This has the closest product fit of the four: LATAM-only talent, US B2B SaaS,
high-value GTM functions and recruiter-mediated applications.

### Technical access

LatamCent's live job links use the official Ashby board name `latamcent`, for
example `https://jobs.ashbyhq.com/latamcent/...`. Ashby's
[Public Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api)
documents:

- `GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}`;
- no API key in the public endpoint contract;
- one response containing currently published postings;
- optional `includeCompensation=true`;
- title, location/secondary locations, department/team, `isRemote`,
  `workplaceType`, HTML/plain description, ISO publication date,
  `employmentType`, address, official job/apply URLs and compensation details.

This is a **PUBLIC_ATS_ENDPOINT** suitable for one bounded weekly request. It is
materially safer than parsing LatamCent's WordPress careers UI. The board is an
agency corpus, so lifecycle should remain observational unless snapshot
completeness is later proven. Company names may be confidential or represented
by LatamCent, and no client identity should be inferred from descriptions.

### Data quality

| Field | Status | Evidence |
|---|---|---|
| Title, location, remote, description, date, employment type, job/apply URL | VERIFIED | Ashby public posting contract |
| Salary | VERIFIED when published | `includeCompensation=true`; absence remains UNKNOWN |
| External ID | PARTIAL | stable posting/job URL exists; exact exposed ID must be fixture-verified |
| Company | PARTIAL | agency/client confidentiality can obscure client identity |
| LATAM/Brazil eligibility | PARTIAL | locations are structured/textual per role; evaluate individually |
| Timezone restriction | UNKNOWN | not part of the public posting contract |

Expected value is **VERY_HIGH**. Etapa 13H.4 implemented an Ashby public-board
source/adapter reusable by explicit tenants and registered LatamCent as the
first observational agency instance. No agency-specific HTML adapter was added.

## Automation classification and access actions

- `PUBLIC_ATS_ENDPOINT`: LatamCent/Ashby only.
- `OFFICIAL_ACCESS_REQUIRED`: HireLATAM/Recruiterflow.
- `PARTNER_ACCESS_REQUIRED`: Somewhere/RecruitCRM.
- `UNKNOWN` (manual until clarified): Near.

Access requests should ask only for read-only published-job access, weekly
unattended permission, limits, pagination/snapshot semantics and attribution.
Never request candidate data, application write access, client-confidential
roles or an employee's credential.

## Future `publisher_model` capability

A future orthogonal capability is justified:

```text
publisher_model:
  JOB_BOARD
  RECRUITING_AGENCY
  TALENT_MARKETPLACE
  DIRECT_EMPLOYER
  ATS
```

It should not replace `SourceType`. `SourceType` describes execution topology,
while `publisher_model` explains ownership, attribution, client confidentiality
and expected lifecycle authority. For example, LatamCent is a tenant-scoped
Ashby board technically, but its publisher model is `RECRUITING_AGENCY`; a
customer's Greenhouse board is `ATS` plus `DIRECT_EMPLOYER`. No enum/model change
belongs in 13H.3.

## Source Outcome Quality — design only

Discovery contribution answers which source found unique relevant jobs. It does
not answer where Daniel should invest application effort. A later
`Source Outcome Quality` layer should attach the source observation selected at
application time to a small outcome funnel:

```text
opportunities_discovered
→ opportunities_marked_keep
→ applications
→ recruiter_screens
→ hiring_manager_interviews
→ interviews
→ final_interviews
→ offers

terminal outcomes: rejections, withdrawals
```

Candidate metrics, computed for explicit cohorts and time windows, include:

- `application_to_screen_rate = recruiter_screens / applications`
- `screen_to_interview_rate = interviews / recruiter_screens`
- `application_to_interview_rate = interviews / applications`
- `application_to_offer_rate = offers / applications`

Rules for a safe first version:

1. Store the source chosen for the application, not merely the current primary
   source after deduplication. Preserve all observations for audit.
2. Distinguish discovery metrics (coverage, KEEP rate, overlap) from outcome
   metrics (human progress after application).
3. Use cohort dates and allow enough maturation time; a fresh application is
   not a rejection or failed screen.
4. Show raw numerator/denominator beside every rate and use `N/A` for zero
   denominators.
5. Treat tiny samples as descriptive only. Do not rank, disable, reweight or
   reprioritize sources automatically. A reasonable initial display guard is
   fewer than 20 applications = “insufficient sample”, subject to later review.
6. Separate withdrawals and candidate decisions from employer rejection; do not
   collapse every terminal state into source failure.
7. Avoid causal claims: role mix, seniority, application quality, timing and
   employer selectivity confound source comparisons.

The future operational question is: **which sources yield more human recruiting
progress per application?** It complements, rather than replaces, source
contribution.

## 13H.4 recommendation

**13H.4 — LatamCent official Ashby board integration (implemented offline)**:

1. validate one real public Ashby response shape safely;
2. build offline fixtures and a generic Ashby public-board adapter;
3. configure only the explicit `latamcent` board;
4. use one request, optional documented compensation, direct Ashby URLs and
   observational lifecycle;
5. preserve confidential/unknown company identity rather than inventing it;
6. add no new scoring or geographic assumptions.

In parallel, Daniel can send a non-technical access request to HireLATAM and
Near. Those requests do not block 13H.4.

## 13H.5 follow-up: Ashby tenant expansion

The follow-up study found no second agency/recruiting Ashby publisher with the
same evidence quality as LatamCent. Fifteen confirmed company tenants were
evaluated separately. ElevenLabs and Replit have the strongest current
Brazil/LATAM GTM evidence and form the recommended two-tenant future pilot;
Vanta remains ambiguous because a LATAM territory title does not establish
worker location. Details: [`ASHBY_TENANT_RESEARCH.md`](ASHBY_TENANT_RESEARCH.md).
