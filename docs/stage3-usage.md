# Stage 3 document usage

Admin upload accepts UTF-8 `.txt`, `.md`, or text-based `.pdf` up to 2 MiB, 40 PDF pages, 100,000 extracted characters and 100 passages. Scanned PDFs without extractable text are rejected. Select a service and permitted roles. Use **Replace** to submit a new file, **Reindex** after changing embedding mode, or **Delete** to remove passages. Replacements and reindexing invalidate the old source IDs in one transaction. Source inspection checks both service membership and document role again.

The idempotent synthetic corpus contains a checkout pool runbook, an ambiguous deployment review, and a restricted payments runbook without real credentials. A viewer cannot read the restricted runbook; an approver with payments service membership can. Hybrid search uses pgvector cosine candidates and PostgreSQL full-text candidates, fuses their ranks, and returns up to ten inspectable passages. It retrieves evidence, not a generated answer.

If the document model changes, old documents are excluded from search until reindexed with the new mode. The embedding cache retains vectors and content hashes only. Extracted document text is stored in PostgreSQL; use synthetic or non-sensitive local test documents.
