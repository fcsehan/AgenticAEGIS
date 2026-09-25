# Security boundary and known limitations

This initial public snapshot is a laboratory research implementation. Its example
domains demonstrate modeled policy semantics; they are not legal, clinical or
operational advice and have not been validated for production deployment.

## What is evaluated

Actions and finite plans are checked against loaded MELD rules. A host must route
every relevant effect through the guard and execute only the exact checked action.
Only `PERMITTED` authorizes execution. The guard cannot make an unmediated host
path safe or establish that a tool call correctly represents a user's intent.

Plan timing uses declared durations, not enforced wall-clock deadlines. State
snapshots are caller declarations, not verified observations. Aggregate bounds
apply within one plan. Obligation coverage is opt-in and does not create intentions
or track persistent follow-up duties. Natural-language-to-MELD fidelity requires
review. Pattern-based output filtering is defense in depth, not a formal proof of
non-disclosure. TLA+ models and regression tests are distinct evidence layers.

## Known issues retained from the source snapshot

These are documented, not silently fixed during the repository extraction:

1. **Missing permission in a known domain:** currently returns `FORBIDDEN` with
   `CWA_NO_PERMISSION`. The proposed stronger distinction using `UNDECIDABLE`
   has not been implemented. Do not claim that every forbidden verdict is an
   explicit prohibition. Broker behavior must be reviewed before changing this.
2. **Unresolved legacy conflicts:** can return the correct `UNDECIDABLE` decision
   with an incorrect `CWA_NO_PERMISSION` reason rather than `UNRESOLVED_CONFLICT`.
3. **Guard hot reload:** the legacy fallback can change an obligatory action's
   verdict after `Guard.reload`. For this snapshot, construct a new Guard from
   the complete MELD sources instead of using hot reload. The editor creates
   guards from source revisions.
4. **Generic guard audit:** rulebase version fields are not fully populated and
   plan-level verdicts are not independently recorded in the generic audit trail.
   Step records alone do not reconstruct a rejected plan. Editor revision records
   do not imply that every guard audit path has equivalent provenance.
5. **Ontology support:** MELD supports structural hierarchies, but there is no
   standard OWL/FHIR/FIBO/SNOMED importer. Resource-parameter subsumption must not
   be assumed from the existence of an ontology hierarchy alone.

The local editor is single-user and loopback-only. `localOperator` is not an
independent reviewer identity. External inference needs an explicitly reviewed
editor policy; profile configuration alone does not authorize data transfer.

See [SECURITY.md](../SECURITY.md) for private vulnerability reporting.
