"""Quick diagnostic: load the real spec and print grouped findings."""
from pathlib import Path
from collections import defaultdict
from report_spec import load_spec, Severity

HERE = Path(__file__).parent
result = load_spec(HERE / "insurance-report-spec.yaml", strict=False)

print(f"is_valid : {result.is_valid}")
print(f"errors   : {len(result.errors)}")
print(f"warnings : {len(result.warnings)}\n")

by_rule: dict[str, list] = defaultdict(list)
for f in result.findings:
    by_rule[f.rule_id].append(f)

for rule_id, findings in sorted(by_rule.items()):
    print(f"── {rule_id} ({len(findings)}) ──")
    for f in findings:
        tag = "ERR" if f.severity == Severity.ERROR else "WRN"
        print(f"  [{tag}] {f.location}: {f.message}")
    print()

if result.spec:
    print(f"Parts    : {[p.part_id for p in result.spec.parts]}")
    print(f"Hybrid   : {[s.subsection_id for _,s in result.spec.hybrid_subsections()]}")
    print(f"Derived  : {sorted(result.spec.derived_variables())}")
