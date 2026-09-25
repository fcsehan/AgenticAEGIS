"""AEGIS-2500: Multi-domain embedding model benchmark.

Evaluates sentence-transformer models against term pairs from all 6
AEGIS domains. Run once to determine the best model for DIP.

Usage:
    python tests/dip/benchmark_embeddings.py
"""

from __future__ import annotations

import time

import numpy as np

# ── Multi-domain term pairs ─────────────────────────────────────────
# Each pair: (term_a, term_b, expected_match: bool)
# Covers English paraphrase matching across six domains

POSITIVE_PAIRS: list[tuple[str, str, str]] = [
    # ── Data protection ───────────────────
    ("controller", "data controller", "legal"),
    ("individual concerned", "data subject", "legal"),
    ("processor", "data processor", "legal"),
    ("privacy officer", "data protection officer", "legal"),
    ("regulatory authority", "supervisory authority", "legal"),
    ("erasure of personal data", "deletion of personal data", "legal"),
    ("authorization", "consent", "legal"),
    ("data processing", "processing", "legal"),
    ("right to inspect personal data", "right of access", "legal"),
    ("third-country data transfer", "transfer to third country", "legal"),

    # ── Military ──────────────────────────────
    ("engagement rules", "rules of engagement", "military"),
    ("commanding officer", "commander", "military"),
    ("intelligence specialist", "intelligence analyst", "military"),
    ("security classification", "classification level", "military"),
    ("information disclosure", "release of information", "military"),
    ("proportionate use of force", "proportionality of force", "military"),
    ("civilian protection", "protection of civilians", "military"),
    ("operational report", "mission report", "military"),

    # ── Medical ───────────────────────────────
    ("untoward medical event", "adverse event", "medical"),
    ("clinical study", "clinical trial", "medical"),
    ("informed authorization", "informed consent", "medical"),
    ("drug safety monitoring", "pharmacovigilance", "medical"),
    ("medical equipment", "medical device", "medical"),
    ("discontinuing treatment", "treatment discontinuation", "medical"),
    ("medical record", "patient record", "medical"),
    ("adverse reaction", "side effect", "medical"),

    # ── IT-Security / Information Security ──────────────
    ("access management", "access control", "it-security"),
    ("data encryption", "encryption", "it-security"),
    ("security vulnerability analysis", "vulnerability assessment", "it-security"),
    ("information security event", "security incident", "it-security"),
    ("event logging", "logging", "it-security"),
    ("recovery after disaster", "disaster recovery", "it-security"),
    ("authentication with two factors", "two-factor authentication", "it-security"),
    ("security penetration testing", "penetration test", "it-security"),

    # ── Finance ──────────────────────────────
    ("diligence checks", "due diligence", "finance"),
    ("prevention of money laundering", "anti-money laundering", "finance"),
    ("trading on inside information", "insider trading", "finance"),
    ("required capital", "capital requirement", "finance"),
    ("risk evaluation", "risk assessment", "finance"),
    ("audit findings report", "audit report", "finance"),

    # ── Corporate ─────────────────────────
    ("staff member", "employee", "corporate"),
    ("company director", "managing director", "corporate"),
    ("company policy", "corporate policy", "corporate"),
    ("sensitive company information", "confidential information", "corporate"),
    ("conflicting interests", "conflict of interest", "corporate"),
    ("conduct rules", "code of conduct", "corporate"),
    ("complaints process", "complaint procedure", "corporate"),

    # ── Additional English legal paraphrases ────────────────
    ("party controlling data", "data controller", "legal-variants"),
    ("right to delete personal data", "right to erasure", "legal-variants"),
    ("authorization to process data", "consent", "legal-variants"),
    ("oversight authority", "supervisory authority", "legal-variants"),
    ("processing personal information", "data processing", "legal-variants"),
]

NEGATIVE_PAIRS: list[tuple[str, str, str]] = [
    # Cross-domain pairs that should NOT match
    ("regulatory authority", "delete data", "legal-vs-action"),
    ("authorization", "processor", "legal-vs-role"),
    ("commander", "personal data", "military-vs-legal"),
    ("adverse event", "access control", "medical-vs-it"),
    ("clinical trial", "insider trading", "medical-vs-finance"),
    ("encryption", "pharmacovigilance", "it-vs-medical"),
    ("due diligence", "informed consent", "finance-vs-medical"),
    ("staff member", "data encryption", "corporate-vs-it"),
    ("engagement rules", "medical record", "military-vs-medical"),
    ("money laundering", "medical device", "finance-vs-medical"),
    ("data controller", "penetration test", "legal-vs-it"),
    ("code of conduct", "disaster recovery", "corporate-vs-it"),
    ("erasure", "commanding officer", "legal-vs-military"),
    ("employee", "clinical trial", "corporate-vs-medical"),
    ("risk assessment", "data subject", "finance-vs-legal"),
    ("conduct rules", "adverse reaction", "corporate-vs-medical"),
    ("conflict of interest", "rules of engagement", "corporate-vs-military"),
    ("diligence checks", "access management", "finance-vs-it"),
    ("prevention of money laundering", "civilian protection", "finance-vs-military"),
    ("company director", "drug safety monitoring", "corporate-vs-medical"),
]

# ── Model candidates ────────────────────────────────────────────────

MODELS = [
    "sentence-transformers/distiluse-base-multilingual-cased-v1",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    "intfloat/multilingual-e5-base",
]


def benchmark_model(model_name: str) -> dict:
    """Benchmark a single model against all term pairs."""
    from sentence_transformers import SentenceTransformer

    print(f"\n{'='*70}")
    print(f"Model: {model_name}")
    print(f"{'='*70}")

    t0 = time.time()
    model = SentenceTransformer(model_name)
    load_time = time.time() - t0
    print(f"  Load time: {load_time:.1f}s")

    # Collect all unique texts
    all_texts = set()
    for a, b, _ in POSITIVE_PAIRS + NEGATIVE_PAIRS:
        # e5 models need "query: " prefix
        if "e5" in model_name:
            all_texts.add(f"query: {a}")
            all_texts.add(f"query: {b}")
        else:
            all_texts.add(a)
            all_texts.add(b)

    # Batch encode
    text_list = sorted(all_texts)
    t0 = time.time()
    embeddings = model.encode(text_list, normalize_embeddings=True, show_progress_bar=False)
    encode_time = time.time() - t0
    ms_per_text = (encode_time / len(text_list)) * 1000
    print(f"  Encode: {len(text_list)} texts in {encode_time:.2f}s ({ms_per_text:.1f}ms/text)")

    # Build lookup
    emb_map = {text: emb for text, emb in zip(text_list, embeddings)}

    def get_emb(text: str) -> np.ndarray:
        if "e5" in model_name:
            return emb_map[f"query: {text}"]
        return emb_map[text]

    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # already normalized

    # Score positive pairs
    pos_scores = []
    pos_by_domain: dict[str, list[float]] = {}
    for a, b, domain in POSITIVE_PAIRS:
        score = cosine(get_emb(a), get_emb(b))
        pos_scores.append(score)
        pos_by_domain.setdefault(domain, []).append(score)

    # Score negative pairs
    neg_scores = []
    for a, b, _ in NEGATIVE_PAIRS:
        score = cosine(get_emb(a), get_emb(b))
        neg_scores.append(score)

    mean_pos = np.mean(pos_scores)
    mean_neg = np.mean(neg_scores)
    separation = mean_pos - mean_neg
    min_pos = np.min(pos_scores)
    max_neg = np.max(neg_scores)

    # Find optimal threshold (maximize F1)
    best_f1 = 0.0
    best_threshold = 0.5
    for thresh in np.arange(0.20, 0.90, 0.01):
        tp = sum(1 for s in pos_scores if s >= thresh)
        fp = sum(1 for s in neg_scores if s >= thresh)
        fn = sum(1 for s in pos_scores if s < thresh)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh

    # Accuracy at optimal threshold
    correct = sum(1 for s in pos_scores if s >= best_threshold) + \
              sum(1 for s in neg_scores if s < best_threshold)
    total = len(pos_scores) + len(neg_scores)
    accuracy = correct / total

    print(f"\n  Results:")
    print(f"    Mean positive:  {mean_pos:.3f}")
    print(f"    Mean negative:  {mean_neg:.3f}")
    print(f"    Separation:     {separation:.3f}")
    print(f"    Min positive:   {min_pos:.3f}")
    print(f"    Max negative:   {max_neg:.3f}")
    print(f"    Optimal thresh: {best_threshold:.2f} (F1={best_f1:.3f}, Acc={accuracy:.1%})")

    print(f"\n  Per-domain positive means:")
    for domain in sorted(pos_by_domain):
        scores = pos_by_domain[domain]
        print(f"    {domain:20s}: {np.mean(scores):.3f} (min={np.min(scores):.3f}, n={len(scores)})")

    # Show worst positive pairs (lowest similarity)
    scored_pos = sorted(zip(pos_scores, POSITIVE_PAIRS), key=lambda x: x[0])
    print(f"\n  Worst 5 positive pairs (lowest similarity):")
    for score, (a, b, domain) in scored_pos[:5]:
        print(f"    {score:.3f}  {a!r} ↔ {b!r}  [{domain}]")

    # Show worst negative pairs (highest similarity)
    scored_neg = sorted(zip(neg_scores, NEGATIVE_PAIRS), key=lambda x: -x[0])
    print(f"\n  Worst 5 negative pairs (highest similarity — false positives):")
    for score, (a, b, domain) in scored_neg[:5]:
        print(f"    {score:.3f}  {a!r} ↔ {b!r}  [{domain}]")

    return {
        "model": model_name,
        "mean_positive": float(mean_pos),
        "mean_negative": float(mean_neg),
        "separation": float(separation),
        "min_positive": float(min_pos),
        "max_negative": float(max_neg),
        "optimal_threshold": float(best_threshold),
        "best_f1": float(best_f1),
        "accuracy": float(accuracy),
        "load_time_s": load_time,
        "ms_per_text": ms_per_text,
        "pos_by_domain": {d: float(np.mean(s)) for d, s in pos_by_domain.items()},
    }


def main() -> None:
    print("AEGIS-2500: Multi-Domain Embedding Model Benchmark")
    print(f"Positive pairs: {len(POSITIVE_PAIRS)}")
    print(f"Negative pairs: {len(NEGATIVE_PAIRS)}")
    print(f"Models: {len(MODELS)}")

    results = []
    for model_name in MODELS:
        try:
            result = benchmark_model(model_name)
            results.append(result)
        except Exception as e:
            print(f"\n  ERROR: {e}")

    # Summary table
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Model':50s} {'Sep':>6s} {'F1':>6s} {'Acc':>6s} {'Thresh':>7s} {'ms/t':>6s}")
    print("-" * 85)
    for r in sorted(results, key=lambda x: -x["separation"]):
        name = r["model"].split("/")[-1]
        print(
            f"{name:50s} "
            f"{r['separation']:6.3f} "
            f"{r['best_f1']:6.3f} "
            f"{r['accuracy']:5.1%} "
            f"{r['optimal_threshold']:7.2f} "
            f"{r['ms_per_text']:6.1f}"
        )

    # Recommendation
    best = max(results, key=lambda x: x["separation"])
    print(f"\n{'='*70}")
    print(f"RECOMMENDATION: {best['model']}")
    print(f"  Separation: {best['separation']:.3f}")
    print(f"  F1: {best['best_f1']:.3f} at threshold {best['optimal_threshold']:.2f}")
    print(f"  Suggested thresholds:")
    print(f"    role_matching:   {best['optimal_threshold']:.2f}")
    print(f"    action_matching: {best['optimal_threshold'] - 0.05:.2f} (slightly relaxed)")
    print(f"    dedup:           0.95")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
