"""AEGIS-2500 v2: Extended benchmark with BGE-M3, LaBSE, and context enrichment.

Tests English legal paraphrases and context-enriched variants.
Historical results from earlier language datasets do not apply.

Usage:
    python tests/dip/benchmark_embeddings_v2.py
"""

from __future__ import annotations

import time
import numpy as np

# ── English paraphrase pairs; no prior scores are asserted ───────────

CRITICAL_PAIRS: list[tuple[str, str, str]] = [
    # Legal paraphrases
    ("controller", "data controller", "legal"),
    ("processor", "data processor", "legal"),
    ("individual concerned", "data subject", "legal"),
    ("privacy officer", "data protection officer", "legal"),
    ("regulatory authority", "supervisory authority", "legal"),
    ("authorization", "consent", "legal"),
    ("erasure of personal data", "deletion of personal data", "legal"),
    ("right to inspect personal data", "right of access", "legal"),
    ("third-country data transfer", "transfer to third country", "legal"),
    ("data processing", "processing", "legal"),
    # Additional legal paraphrases
    ("party controlling data", "data controller", "legal-variants"),
    ("right to delete personal data", "right to erasure", "legal-variants"),
    ("oversight authority", "supervisory authority", "legal-variants"),
    # Military
    ("engagement rules", "rules of engagement", "military"),
    ("commanding officer", "commander", "military"),
    ("proportionate use of force", "proportionality of force", "military"),
    # Medical
    ("untoward medical event", "adverse event", "medical"),
    ("clinical study", "clinical trial", "medical"),
    ("drug safety monitoring", "pharmacovigilance", "medical"),
    # IT-Security
    ("access management", "access control", "it-security"),
    ("security vulnerability analysis", "vulnerability assessment", "it-security"),
    # Finance
    ("diligence checks", "due diligence", "finance"),
    ("prevention of money laundering", "anti-money laundering", "finance"),
    # Corporate
    ("conduct rules", "code of conduct", "corporate"),
    ("conflicting interests", "conflict of interest", "corporate"),
]

# Same pairs with GDPR/domain context enrichment
CONTEXT_ENRICHED_PAIRS: list[tuple[str, str, str]] = [
    ("controller (GDPR Art. 4(7))", "data controller (GDPR Art. 4(7))", "legal-ctx"),
    ("processor (GDPR Art. 4(8))", "data processor (GDPR Art. 4(8))", "legal-ctx"),
    ("individual concerned (GDPR Art. 4(1))", "data subject (GDPR Art. 4(1))", "legal-ctx"),
    ("regulatory authority (GDPR Art. 51)", "supervisory authority (GDPR Art. 51)", "legal-ctx"),
    ("engagement rules (NATO ROE)", "rules of engagement (NATO ROE)", "military-ctx"),
    ("commanding officer (armed services)", "commander (armed forces)", "military-ctx"),
    ("untoward medical event (medicines regulation)", "adverse event (pharmacovigilance)", "medical-ctx"),
    ("access management (ISO 27001)", "access control (ISO 27001)", "it-ctx"),
    ("diligence checks (financial supervision)", "due diligence (financial regulation)", "finance-ctx"),
]

NEGATIVE_PAIRS: list[tuple[str, str, str]] = [
    ("controller", "delete data", "neg"),
    ("commander", "personal data", "neg"),
    ("adverse event", "access control", "neg"),
    ("encryption", "pharmacovigilance", "neg"),
    ("due diligence", "informed consent", "neg"),
    ("erasure", "commanding officer", "neg"),
    ("staff member", "data encryption", "neg"),
    ("code of conduct", "disaster recovery", "neg"),
]


MODELS = {
    "paraphrase-multilingual-mpnet-base-v2": {
        "type": "sentence-transformers",
        "name": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    },
    "BGE-M3": {
        "type": "sentence-transformers",
        "name": "BAAI/bge-m3",
    },
    "LaBSE": {
        "type": "sentence-transformers",
        "name": "sentence-transformers/LaBSE",
    },
}


def benchmark_model(label: str, spec: dict) -> dict | None:
    from sentence_transformers import SentenceTransformer

    print(f"\n{'='*70}")
    print(f"Model: {label} ({spec['name']})")
    print(f"{'='*70}")

    try:
        t0 = time.time()
        model = SentenceTransformer(spec["name"])
        load_time = time.time() - t0
        print(f"  Load time: {load_time:.1f}s")
    except Exception as e:
        print(f"  FAILED to load: {e}")
        return None

    def encode_pairs(pairs):
        texts_a = [a for a, b, _ in pairs]
        texts_b = [b for a, b, _ in pairs]
        all_texts = texts_a + texts_b
        t0 = time.time()
        embs = model.encode(all_texts, normalize_embeddings=True, show_progress_bar=False)
        encode_time = time.time() - t0
        embs_a = embs[:len(texts_a)]
        embs_b = embs[len(texts_a):]
        scores = [float(np.dot(a, b)) for a, b in zip(embs_a, embs_b)]
        return scores, encode_time

    # Critical pairs (bare terms)
    crit_scores, crit_time = encode_pairs(CRITICAL_PAIRS)
    # Context-enriched pairs
    ctx_scores, ctx_time = encode_pairs(CONTEXT_ENRICHED_PAIRS)
    # Negative pairs
    neg_scores, neg_time = encode_pairs(NEGATIVE_PAIRS)

    ms_per_text = ((crit_time + ctx_time + neg_time) / (len(CRITICAL_PAIRS)*2 + len(CONTEXT_ENRICHED_PAIRS)*2 + len(NEGATIVE_PAIRS)*2)) * 1000

    mean_crit = np.mean(crit_scores)
    mean_ctx = np.mean(ctx_scores)
    mean_neg = np.mean(neg_scores)
    separation_bare = mean_crit - mean_neg
    separation_ctx = mean_ctx - mean_neg

    print(f"\n  Critical pairs (bare terms):     mean={mean_crit:.3f}  min={np.min(crit_scores):.3f}")
    print(f"  Context-enriched pairs:          mean={mean_ctx:.3f}  min={np.min(ctx_scores):.3f}")
    print(f"  Negative pairs:                  mean={mean_neg:.3f}  max={np.max(neg_scores):.3f}")
    print(f"  Separation (bare):               {separation_bare:.3f}")
    print(f"  Separation (context-enriched):   {separation_ctx:.3f}")
    print(f"  Speed: {ms_per_text:.1f}ms/text")

    # Per-domain breakdown for critical pairs
    by_domain: dict[str, list[float]] = {}
    for score, (a, b, domain) in zip(crit_scores, CRITICAL_PAIRS):
        by_domain.setdefault(domain, []).append(score)

    print(f"\n  Per-domain (bare terms):")
    for domain in sorted(by_domain):
        scores = by_domain[domain]
        print(f"    {domain:15s}: mean={np.mean(scores):.3f}  min={np.min(scores):.3f}  n={len(scores)}")

    # The 5 hardest pairs
    scored = sorted(zip(crit_scores, CRITICAL_PAIRS), key=lambda x: x[0])
    print(f"\n  5 hardest pairs (lowest score):")
    for score, (a, b, domain) in scored[:5]:
        print(f"    {score:.3f}  {a!r} ↔ {b!r}  [{domain}]")

    # Context enrichment improvement
    print(f"\n  Context enrichment improvement:")
    for (score_ctx, (a_ctx, b_ctx, _)), (score_bare, (a_bare, b_bare, _)) in zip(
        sorted(zip(ctx_scores, CONTEXT_ENRICHED_PAIRS)),
        sorted(zip(crit_scores[:len(CONTEXT_ENRICHED_PAIRS)], CRITICAL_PAIRS[:len(CONTEXT_ENRICHED_PAIRS)])),
    ):
        pass  # pairs don't align 1:1, do it differently

    # Match context pairs to their bare equivalents
    bare_lookup = {}
    for score, (a, b, domain) in zip(crit_scores, CRITICAL_PAIRS):
        key = (a.split("(")[0].strip().lower(), b.split("(")[0].strip().lower())
        bare_lookup[key] = score

    print(f"\n  Context enrichment delta:")
    for score_ctx, (a_ctx, b_ctx, domain) in zip(ctx_scores, CONTEXT_ENRICHED_PAIRS):
        a_bare = a_ctx.split("(")[0].strip().lower()
        b_bare = b_ctx.split("(")[0].strip().lower()
        score_bare = bare_lookup.get((a_bare, b_bare), None)
        if score_bare is not None:
            delta = score_ctx - score_bare
            print(f"    {delta:+.3f}  {a_ctx[:40]:40s} ({score_bare:.3f} → {score_ctx:.3f})")

    # F1 optimization for bare terms
    best_f1 = 0.0
    best_thresh = 0.5
    for thresh in np.arange(0.10, 0.90, 0.01):
        tp = sum(1 for s in crit_scores if s >= thresh)
        fp = sum(1 for s in neg_scores if s >= thresh)
        fn = sum(1 for s in crit_scores if s < thresh)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    print(f"\n  Optimal threshold: {best_thresh:.2f} (F1={best_f1:.3f})")

    return {
        "model": label,
        "mean_critical": float(mean_crit),
        "mean_context": float(mean_ctx),
        "mean_negative": float(mean_neg),
        "separation_bare": float(separation_bare),
        "separation_ctx": float(separation_ctx),
        "min_critical": float(np.min(crit_scores)),
        "best_f1": float(best_f1),
        "best_threshold": float(best_thresh),
        "ms_per_text": ms_per_text,
    }


def main() -> None:
    print("AEGIS-2500 v2: Extended Benchmark (BGE-M3, LaBSE, context enrichment)")
    print(f"Critical pairs: {len(CRITICAL_PAIRS)}")
    print(f"Context-enriched: {len(CONTEXT_ENRICHED_PAIRS)}")
    print(f"Negative pairs: {len(NEGATIVE_PAIRS)}")

    results = []
    for label, spec in MODELS.items():
        r = benchmark_model(label, spec)
        if r:
            results.append(r)

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Model':45s} {'Sep(bare)':>10s} {'Sep(ctx)':>10s} {'F1':>6s} {'MinPos':>7s} {'ms/t':>6s}")
    print("-" * 90)
    for r in sorted(results, key=lambda x: -x["separation_bare"]):
        print(
            f"{r['model']:45s} "
            f"{r['separation_bare']:10.3f} "
            f"{r['separation_ctx']:10.3f} "
            f"{r['best_f1']:6.3f} "
            f"{r['min_critical']:7.3f} "
            f"{r['ms_per_text']:6.1f}"
        )

    best = max(results, key=lambda x: x["separation_bare"])
    print(f"\nRECOMMENDATION: {best['model']}")
    print(f"  Bare separation: {best['separation_bare']:.3f}")
    print(f"  Context-enriched separation: {best['separation_ctx']:.3f}")


if __name__ == "__main__":
    main()
