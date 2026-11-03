"""Small retrieval smoke/evaluation script; checks expected source sections."""
from app.rag.retrieval import POLICY_DIR, index_policy_file, search_policy


CASES = [
    ("List the academic transcript, marksheet, and proof of enrollment requested by the synthetic checklist.", "Required supporting documents"),
    ("Does this demo define an academic mark threshold?", "No academic score threshold"),
    ("Who must compare the original document with official instructions before relying on it?", "Human review and limitations"),
]


def main() -> None:
    index_policy_file(POLICY_DIR / "demo_scholarship_policy.md")
    failures = []
    for question, expected_section in CASES:
        result = search_policy(question, "demo-scholarship")
        sections = [source["section"] for source in result["sources"]]
        passed = expected_section in sections
        print(f"{'PASS' if passed else 'FAIL'}: {question} -> {sections}")
        if not passed:
            failures.append(question)
    if failures:
        raise SystemExit(f"{len(failures)} retrieval case(s) failed")
    print(f"All {len(CASES)} retrieval cases matched their expected section.")


if __name__ == "__main__":
    main()
