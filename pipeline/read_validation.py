"""Read and display validation report summary."""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, 'output', 'motor_shaft_1001_validation.json'), 'r') as f:
    report = json.load(f)

print("=" * 70)
print("Validation Report Summary")
print("=" * 70)

print(f"\nStatus: {report['summary']['status']}")
print(f"Total violations: {report['summary']['total_violations']}")
print(f"Errors: {report['summary']['errors']}")
print(f"Warnings: {report['summary']['warnings']}")

print(f"\nBlocks executed: {report['statistics']['blocks_executed']}")
print(f"Tool changes: {report['statistics']['tool_changes']}")
print(f"Total travel: {report['statistics']['total_travel_distance']:.2f}mm")
print(f"Cut distance: {report['statistics']['cut_distance']:.2f}mm")

# Group violations by category
categories = {}
for v in report['violations']:
    cat = v['category']
    sev = v['severity']
    if cat not in categories:
        categories[cat] = {}
    if sev not in categories[cat]:
        categories[cat][sev] = 0
    categories[cat][sev] += 1

print(f"\nViolations by Category:")
for cat, counts in sorted(categories.items()):
    total = sum(counts.values())
    print(f"  {cat}: {total} violations ({counts.get('error', 0)} errors, {counts.get('warning', 0) + counts.get('WARNING', 0)} warnings)")

# Print all errors
print(f"\nError Details:")
for v in report['violations']:
    if v['severity'] in ['error', 'ERROR']:
        print(f"  Line {v['line_number']}: {v['message']}")
