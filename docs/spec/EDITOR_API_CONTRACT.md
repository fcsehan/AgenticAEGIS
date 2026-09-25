# Web editor: source and API contract

Snapshot: 2026-09-25. Machine-readable request schemas are served by the running
editor at `/openapi.json`. Frontend projections are not the normative data store.

| User action | API | Persistent reference |
|---|---|---|
| Open/create/close project | POST `/api/project/{open,create,close}`, GET `/api/project` | Workspace and session.json |
| List/create domains | GET/POST `/api/domains`, GET `/api/domains/{id}` | Original or current MELD snapshots |
| Metadata/archiving | GET/PUT `…/{id}/metadata` | Separate metadataRevision, domain.json |
| Package import | POST `/api/project/import/preview`, POST `/api/project/import` | Validated source hash, new directory |
| Save/export sources | GET/PUT `…/{id}/sources`, GET `…/{id}/export` | SHA-256 revision, complete MELD files |
| Edit structure | POST `…/{id}/structure` | Revision and source changes preserving symbol references |
| Code precedence | POST `…/{id}/code-prevalence` | Schema 1 MELD declaration |
| Edit rules | POST/PUT `…/{id}/source-rules[/{ruleId}]`, POST `…/{ruleId}/delete` | Source position and expected revision |
| Plan constraints | GET/POST `…/{id}/plan-constraints` | Source position and expected revision |
| Diagnostics | GET `…/{id}/{validate,conflicts}` | Actual Guard and identified validation scope |
| Check actions/plans | POST `…/{id}/{check,plan_check}` | Current saved draft |
| Scenarios | GET/PUT `…/{id}/scenarios`, POST `…/{id}/scenarios/run` | Inputs, expectations, revision, result hash |
| Configure providers | GET/PUT `/api/llm/settings` | schemaVersion=1, revision, no secret values |
| Connection/capabilities | POST `/api/llm/profiles/{id}/{probe,capability}` | Profile revision and model, temporary evidence |
| Generate/refine proposals | POST `…/{id}/jobs/{generate,refine}` | Session record; explicit adoption is separate |
| Read/cancel jobs | GET `/api/jobs/{id}`, POST `…/{id}/cancel` | No normative state |
| Verify/adopt proposals | POST `…/{id}/verify`, POST `…/{id}/proposals/accept` | Four stages, complete snapshot, revision |
| Review/release/activation | GET `…/{id}/governance`, POST `…/governance/{review,publish,activate}` | Immutable source data and evidence |
| Check active runtime | POST `…/{id}/runtime/check` | Published active version, not draft |
| DIP | POST `/api/dip/jobs`, POST `/api/dip/jobs/{id}/adopt` | Pipeline report, source hash, new draft |

Legacy transient rule CRUD endpoints are disabled for real source domains.
A status patch cannot publish a release. No Git files are added, reset or checked out.

## Shared fields

- Project: `path`, `name`, `loadedAt`, `meldFiles[]` with path/name/type/size,
  `domains[]`. The production client contains no mock data.
- Domain: editing projections `roles`, `codes`, `obligationTypes`, `rules`,
  `actionTypes`, `actionSchemas`, `codePrevalence`, `revision`, `loadError`.
  Unknown or symbolic constructs are preserved in full in `sources`.
- Action: `agent`, `actionType`, `parameters`, optional `context`.
- Verdict: `decision`, `reasonType`, `justificationChain`, `revision`;
  additional explanatory fields do not change the decision.
- Errors: HTTP status and `detail`. 409 means a stale revision or missing workflow
  prerequisite; 422 means invalid input; 403 means a formal or transport boundary;
  503 means unavailable mediation or audit. Validation errors do not repeat input
  credential values. Core Project/Domain/Sources/Verdict responses have Pydantic
  models in `aegis/editor/contracts.py`. Diagnostics, jobs and governance use
  additional JSON projections.

## Schema 1 MELD extension: codePrevalence

```lisp
(aegis-schema-version 1)
(case OrganizationCodesMt)
(isa OrganizationCode CodeOfConduct)
(isa EmergencyCode CodeOfConduct)
(codePrevalence EmergencyCode OrganizationCode)
```

A domain may contain exactly one nonempty, duplicate-free `codePrevalence`
declaration, with highest priority first. Codes must be declared or known from
norms. Unlisted codes share the lowest rank. The declaration sets the existing
`DDICModule.code_prevalence` value for the **legacy** strategy; it does not change
the resolution algorithm.

Without a declaration, previous behavior is unchanged. Providing Python
`code_prevalence=` alongside a MELD declaration is rejected so MELD remains the
single source. Schema 2 still uses `(priority A B)` on formulas; schema 1 code
orders are not reinterpreted as formula priorities. Unknown codes, duplicate
entries or multiple declarations prevent loading. Export and the CLI Guard use
the same declaration as the editor.

Domain responses also include `compileStatus` (`ready`, `failed`, `uncompiled`)
and `loadError`. A failed draft does not silently receive a successful check
from an older Guard.
