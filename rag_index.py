"""
ChromaDB retrieval for Task 1 -- supplier emails specifically.

WHY EMAILS AND NOT THE NUMBERS: warehouse stock, CRM commitments, and
freight tracker figures are exact numeric facts -- there's nothing to
"retrieve" semantically, and NO_GUESSING_RULE requires the agent only
ever use numbers straight from the tools, never anything reconstructed
via similarity search. Supplier emails are free-text and informal by
nature ("the drying yard is running behind... may slip a few days"),
which is exactly the kind of unstructured content retrieval-augmented
search is meant for. The deterministic delay flag (mentions_delay) stays
the ground truth either way -- ChromaDB's job here is only to surface
*which* email is most relevant to a delay-related question and why,
not to decide whether a delay is happening.
"""

import chromadb
import pandas as pd

DATA_DIR = "data"
_client = chromadb.Client()  # in-memory, rebuilt each run from the CSV
_COLLECTION_NAME = "supplier_emails"


def build_supplier_email_index():
    """Loads supplier_emails.csv into a ChromaDB collection, embedding
    each email's subject + note as one document. Rebuilding each run
    keeps it in sync with generate_data.py's latest output -- no stale
    index to manage."""
    try:
        _client.delete_collection(_COLLECTION_NAME)
    except Exception:
        pass  # collection doesn't exist yet, nothing to delete
    collection = _client.create_collection(_COLLECTION_NAME)

    df = pd.read_csv(f"{DATA_DIR}/supplier_emails.csv")
    documents = (df["subject"] + ". " + df["note"]).tolist()
    ids = df["email_id"].tolist()
    metadatas = df.to_dict(orient="records")

    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    return collection


def query_supplier_emails(query_text: str = "shipment delay disruption running behind schedule", n_results: int = 2) -> list:
    """Semantic search over supplier emails -- returns the most relevant
    email(s) to a delay-related question, ranked by similarity. This is
    retrieval, not a fact -- always cross-check against the deterministic
    mentions_delay flag from check_supplier_emails() for the ground truth
    of whether a delay is actually flagged."""
    collection = build_supplier_email_index()
    results = collection.query(query_texts=[query_text], n_results=n_results)

    matches = []
    for i in range(len(results["ids"][0])):
        matches.append({
            "email_id": results["ids"][0][i],
            "similarity_distance": round(results["distances"][0][i], 4),
            "subject": results["metadatas"][0][i]["subject"],
            "note": results["metadatas"][0][i]["note"],
            "mentions_delay": results["metadatas"][0][i]["mentions_delay"],
        })
    return matches


if __name__ == "__main__":
    import json
    print("Testing semantic search for delay-related emails:\n")
    matches = query_supplier_emails()
    print(json.dumps(matches, indent=2, default=str))
