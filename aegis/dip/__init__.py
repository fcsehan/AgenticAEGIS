"""DIP — Document Intelligence Pipeline.

Converts normative documents (laws, standards, policies, codes of conduct)
into complete AEGIS MELD domain rulesets via a 6-stage pipeline:

  1. Fetch — acquire document (HTML/PDF/text) from any source
  2. Chunk — structural recognition, deontic classification
  3. Extract — LLM-based normative statement extraction
  4. Ontology — derive domain roles, actions, object categories
  5. Compile — map statements to MELD RuleProposals
  6. Export — produce 3 .meld files + review report

DIP is domain-agnostic and language-configurable. Signal word profiles
for English are included; custom classification profiles can be provided.
"""
