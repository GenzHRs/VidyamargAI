import json

with open("docs/audit/results/phase_1_before.json", "r", encoding="utf-8") as f1:
    b = json.load(f1)
with open("docs/audit/results/phase_1_after.json", "r", encoding="utf-8") as f2:
    a = json.load(f2)

print("=== OVERALL METRICS COMPARISON ===")
print(f"Total Fixtures:     {a.get('total_fixtures')}")
print(f"Passed:             {b.get('total_passed')} -> {a.get('total_passed')} (+{a.get('total_passed', 0) - b.get('total_passed', 0)})")
print(f"Partial:            {b.get('total_partial')} -> {a.get('total_partial')}")
print(f"Failed:             {b.get('total_failed')} -> {a.get('total_failed')}")
print(f"Pass Rate:          {b.get('pass_rate', 0)*100:.1f}% -> {a.get('pass_rate', 0)*100:.1f}%")
print(f"Strict Precision:   {b.get('overall_strict_precision', 0):.3f} -> {a.get('overall_strict_precision', 0):.3f}")
print(f"Strict Recall:      {b.get('overall_strict_recall', 0):.3f} -> {a.get('overall_strict_recall', 0):.3f} (+{a.get('overall_strict_recall', 0) - b.get('overall_strict_recall', 0):.3f})")
print(f"Strict F1:          {b.get('overall_strict_f1', 0):.3f} -> {a.get('overall_strict_f1', 0):.3f} (+{a.get('overall_strict_f1', 0) - b.get('overall_strict_f1', 0):.3f})")
print(f"Normalized Precision:{b.get('overall_normalized_precision', 0):.3f} -> {a.get('overall_normalized_precision', 0):.3f}")
print(f"Normalized Recall:  {b.get('overall_normalized_recall', 0):.3f} -> {a.get('overall_normalized_recall', 0):.3f} (+{a.get('overall_normalized_recall', 0) - b.get('overall_normalized_recall', 0):.3f})")
print(f"Normalized F1:      {b.get('overall_normalized_f1', 0):.3f} -> {a.get('overall_normalized_f1', 0):.3f} (+{a.get('overall_normalized_f1', 0) - b.get('overall_normalized_f1', 0):.3f})")

print("\n=== FORMAT BREAKDOWN ===")
for fmt, fa in a.get("format_breakdown", {}).items():
    fb = b.get("format_breakdown", {}).get(fmt, {})
    br = fb.get("normalized_mean_recall", 0)
    ar = fa.get("normalized_mean_recall", 0)
    bf = fb.get("normalized_mean_f1", 0)
    af = fa.get("normalized_mean_f1", 0)
    print(f"{fmt.upper():6s} | Norm Recall: {br:.3f} -> {ar:.3f} ({ar-br:+.3f}) | Norm F1: {bf:.3f} -> {af:.3f} ({af-bf:+.3f})")

print("\n=== FIXTURES WITH SIGNIFICANT IMPROVEMENTS ===")
b_map = {r["test_id"]: r for r in b.get("results", [])}
for r in a.get("results", []):
    tid = r["test_id"]
    if tid in b_map:
        br = b_map[tid]["metrics"]["normalized_recall"]
        ar = r["metrics"]["normalized_recall"]
        bs = b_map[tid]["actual_status"]
        as_ = r["actual_status"]
        fn = r.get("file_name", "")
        if abs(ar - br) >= 0.01 or bs != as_:
            print(f"{tid:6s} ({fn:35s}): status {bs:7s} -> {as_:7s} | Norm Recall: {br:.3f} -> {ar:.3f} ({ar-br:+.3f})")
