# Scope of the AEGIS guarantee

The guard evaluates modeled actions and finite plans against the loaded formal
rulebase. Only `PERMITTED` authorizes execution. A host must mediate every relevant
effect and execute precisely the checked action for that boundary to hold.

This does not guarantee the correctness of natural-language interpretation,
ontology mappings, classifications, caller-supplied state, or the rulebase itself.
Unmediated channels remain outside the guarantee. Pattern-based output filtering
is defense in depth and cannot establish formal non-disclosure.

Conformance test results support only the cases and assumptions they exercise.
The presence of TLA+ model files is not evidence that TLC has been run on this
release. A green repository-artifact claim gate is not a production security
certification or a proof of complete host coverage.

The current snapshot has known permission, conflict-reason, reload and audit
limitations. These are specified in [limitations](../limitations.md). See also
the [validation scope](../validation.md) and [release record](../release.md).
