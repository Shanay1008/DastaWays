from app.rag.retrieval import POLICY_DIR, index_policy_file


def main() -> None:
    policy = POLICY_DIR / "demo_scholarship_policy.md"
    count = index_policy_file(policy)
    print(f"Indexed {count} chunks from {policy.name} as a synthetic demo source.")


if __name__ == "__main__":
    main()
