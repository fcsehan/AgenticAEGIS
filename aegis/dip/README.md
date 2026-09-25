# DIP — Document Intelligence Pipeline

Converts **any normative document** (laws, regulations, standards, corporate
policies, codes of conduct, engagement rules) into a complete AEGIS MELD
domain ruleset.

## 6-Stage Pipeline

```
NormativeDocument (HTML / PDF / Text / Markdown)
    │
    ▼ Stage 1: Fetcher (deterministic)
NormativeDocument (structured articles)
    │
    ▼ Stage 2: Chunker (deterministic)
NormativeChunks (classified by deontic function)
    │
    ▼ Stage 3: Extractor (LLM)
NormativeStatements (subject, modality, action, conditions)
    │
    ▼ Stage 4: Ontology Builder (LLM)
DomainOntology (roles, actions, categories, hierarchy)
    │
    ▼ Stage 5: Rule Compiler (deterministic)
CompilationResults (validated MELD expressions)
    │
    ▼ Stage 6: Domain Exporter (deterministic)
3 MELD files + review report → aegis/domains/{name}/
    │
    ▼ Guard.from_meld_files()
Guard with rules → check(action) → Verdict
```

## Supported Input Types

| Type | Example | Detection |
|---|---|---|
| HTML Index | `https://example.com/policies/topics/` | URL with /topics/, /index |
| HTML Page | `https://example.com/policy.html` | URL ending in .html |
| Markdown | `./company-policy.md` | .md extension |
| Plain Text | `./regulation.txt` | .txt extension |
| PDF | `./standard.pdf` | .pdf extension (requires pymupdf) |

## Input language

The `en` signal-word profile classifies English input. `auto` selects this
profile. Custom classification profiles can be supplied programmatically.

## CLI Usage

```bash
# English corporate policy → MELD domain
aegis dip ./company-policy.md \
    --name corporate \
    --output aegis/domains/corporate/ \
    --language en \
    --provider lm-studio --model qwen/qwen3.8-27b

# English regulation from a local file
aegis dip ./gdpr-extract.md \
    --name gdpr \
    --language en \
    --domain-context "GDPR data protection requirements" \
    --provider anthropic --model claude-sonnet-4-6

# ISO standard from local file
aegis dip ./iso27001-controls.txt \
    --name iso27001 \
    --domain-context "ISO 27001 information security controls" \
    --provider openai --model gpt-4o

# Dry run (show proposals without writing files)
aegis dip ./rules.md --name test --dry-run --stats
```

## CLI Flags

| Flag | Description |
|---|---|
| `--name`, `-n` | Domain name (required) |
| `--output`, `-o` | Output directory (default: `aegis/domains/<name>/`) |
| `--source-type` | `auto`, `html`, `html-index`, `text`, `pdf` |
| `--language` | `auto`, `en` |
| `--domain-context` | Domain hints for the LLM |
| `--provider` | `anthropic`, `openai`, `lm-studio`, `ollama` |
| `--model` | Model identifier |
| `--dry-run` | Show results without writing files |
| `--stats` | Show detailed statistics |
| `--batch-size` | Chunks per LLM call (default: 5) |

## Output

DIP produces 4 files in the output directory:

1. **`{Name}DomainOntologyMt.meld`** — Roles, hierarchy, data categories, deontic infrastructure
2. **`{Name}ActionVocabMt.meld`** — Action types with parameters
3. **`{Name}DeonticRulesMt.meld`** — All compiled rules, flagged rules annotated
4. **`{name}-review.json`** — Machine-readable review report

The generated domain loads directly via `Guard.from_meld_files()`.

## Review Report

Rules that need human review are flagged with reasons:

| Flag | Meaning |
|---|---|
| `vague_term` | Indeterminate term (e.g. "appropriate", "without undue delay") |
| `low_confidence` | LLM confidence below threshold (default: 0.7) |
| `unmapped_term` | Subject or action not in ontology |
| `delegation_clause` | Refers to external authority (e.g. "national law") |

## Architecture

```
aegis/dip/
    __init__.py           # Package docstring
    models.py             # Data types for all 6 stages
    fetcher.py            # Stage 1: DocumentSource protocol + implementations
    chunker.py            # Stage 2: SignalWordProfile-based classification
    prompts.py            # LLM tool schemas + system prompts
    extractor.py          # Stage 3: Batch extraction via tool calls
    ontology_builder.py   # Stage 4: Single-call ontology derivation
    rule_compiler.py      # Stage 5: Deterministic compilation + flagging
    domain_exporter.py    # Stage 6: 3 MELD files + review report
    pipeline.py           # Orchestrator (stages 1-6)
```

DIP imports from:
- `aegis.editor` — `LLMClient`, `RuleProposal`, `build_meld_expression()`, `write_action_vocab_meld()`
- `aegis.kb` — `parse_meld()`, `extract_norm()` (for validation)
- `aegis.guard` — `Guard.from_meld_files()` (for end-to-end validation)

DIP is part of **aegis-guard** (it has I/O: HTTP, filesystem, LLM calls).

## Extending

### Custom Signal Word Profile

```python
from aegis.dip.chunker import SignalWordProfile, chunk_document

security_profile = SignalWordProfile(
    language="en-security",
    obligation=(r"\bis required\b",),
    prohibition=(r"\bis forbidden\b",),
    permission=(r"\bis authorized\b",),
    exception=(r"\bunless\b",),
    definition=(r"\bmeans\b",),
)

chunks = chunk_document(doc, profile=security_profile)
```

### Programmatic Usage

```python
from aegis.dip.pipeline import run_pipeline
from aegis.editor.llm_provider import LLMClient, LLMProviderInfo, ModelInfo

provider = LLMProviderInfo(
    id="lm-studio", name="LM Studio", type="local",
    base_url="http://localhost:1234/v1", available=True,
    models=[ModelInfo(id="qwen", name="qwen")],
)
client = LLMClient(provider, "qwen")

export = run_pipeline(
    source="./regulation.md",
    name="my_domain",
    client=client,
    output_dir="./output/",
    domain_context="Healthcare compliance",
)

print(export.summary())
# Domain 'my_domain': 42 rules (18 OBL, 8 FRB, 16 PRM),
# 30 auto-generated, 12 flagged for review, from 25 articles (5 skipped)
```

## Coexistence with Manual Domains (D-015)

DIP-generated domains live under `aegis/domains/dip-generated/<name>/` by
default — strictly separated from manually authored domains under
`aegis/domains/<name>/`.

The pipeline refuses two conflict classes before stage 1:

- **Hard conflict** — target is `aegis/domains/<name>/` *and* a manual
  domain with `.meld` files already exists there. Refused unconditionally;
  `--force` does not override.
- **Soft conflict** — target directory already contains any `.meld`
  files. Refused unless `--force` is passed.

If you want to overlay a manual domain with DIP output, do so explicitly
with `--output` and a different target. The hard-conflict guard exists to
prevent silent overwrites of reviewed, hand-authored rule sets.

See `spec/DECISION_LOG.md` (D-015) and `aegis/dip/coexistence.py`.
