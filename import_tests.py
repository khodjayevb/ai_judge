"""
Import generated test cases from JSON into a Python test suite file.

Usage:
    python import_tests.py generated/azure_data_architect_tests.json --role azure_data_architect
    python import_tests.py generated/tests.json --name custom_tests
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def json_to_test_suite(json_path: str, role_slug: str = None, suite_name: str = None) -> str:
    """Convert a JSON test cases file into a Python test_suites/ file."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError("JSON must be an array of test case objects")

    # Clean up test cases for Python output
    clean_cases = []
    for tc in data:
        clean = {
            "id": tc.get("id", f"GEN-{len(clean_cases)+1:02d}"),
            "category": tc.get("category", "General"),
            "question": tc.get("question", ""),
            "criteria": tc.get("criteria", [])[:5],
            "weight": tc.get("weight", 2),
        }
        # Include context if present
        if tc.get("context"):
            ctx = tc["context"]
            if isinstance(ctx, str):
                ctx = [ctx]
            clean["context"] = ctx
        clean_cases.append(clean)

    # Determine output filename
    name = suite_name or role_slug or "generated"
    output_path = Path(f"test_suites/{name}_generated_tests.py")

    # Generate Python file
    categories = sorted(set(tc["category"] for tc in clean_cases))
    py_content = f'"""\nGenerated test suite for {name}.\nImported from: {json_path}\nTests: {len(clean_cases)} | Categories: {", ".join(categories)}\n\nReview criteria before using in production evaluations.\n"""\n\n'
    py_content += f"TEST_CASES = {json.dumps(clean_cases, indent=4, ensure_ascii=False)}\n\n"
    py_content += 'CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))\n'

    output_path.write_text(py_content, encoding="utf-8")
    return str(output_path.resolve())


def merge_into_existing(json_path: str, role_slug: str) -> str:
    """Merge generated tests into an existing test suite file."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    suite_path = Path(f"test_suites/{role_slug}_tests.py")

    if not suite_path.exists():
        # No existing suite — create new
        return json_to_test_suite(json_path, role_slug=role_slug, suite_name=role_slug)

    # Load existing
    import importlib
    mod = importlib.import_module(f"test_suites.{role_slug}_tests")
    existing = list(mod.TEST_CASES)
    existing_ids = {tc["id"] for tc in existing}

    # Add new, skip duplicates
    added = 0
    for tc in data:
        clean = {
            "id": tc.get("id", f"GEN-{len(existing)+1:02d}"),
            "category": tc.get("category", "General"),
            "question": tc.get("question", ""),
            "criteria": tc.get("criteria", [])[:5],
            "weight": tc.get("weight", 2),
        }
        if tc.get("context"):
            ctx = tc["context"]
            clean["context"] = [ctx] if isinstance(ctx, str) else ctx

        if clean["id"] not in existing_ids:
            existing.append(clean)
            existing_ids.add(clean["id"])
            added += 1

    # Rewrite the file
    categories = sorted(set(tc["category"] for tc in existing))
    py_content = f'"""\nTest suite for {role_slug}.\nTotal tests: {len(existing)} | Categories: {", ".join(categories)}\n"""\n\n'
    py_content += f"TEST_CASES = {json.dumps(existing, indent=4, ensure_ascii=False)}\n\n"
    py_content += 'CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))\n'

    suite_path.write_text(py_content, encoding="utf-8")
    return f"{suite_path.resolve()} ({added} new tests added, {len(existing)} total)"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import generated tests")
    parser.add_argument("json_file", help="Path to generated JSON file")
    parser.add_argument("--role", help="Role slug to merge into existing test suite")
    parser.add_argument("--name", help="Name for new test suite file")
    parser.add_argument("--merge", action="store_true", help="Merge into existing test suite")
    args = parser.parse_args()

    if args.merge and args.role:
        result = merge_into_existing(args.json_file, args.role)
        print(f"Merged: {result}")
    else:
        result = json_to_test_suite(args.json_file, role_slug=args.role, suite_name=args.name)
        print(f"Created: {result}")
