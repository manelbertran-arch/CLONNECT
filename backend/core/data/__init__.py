"""
backend/core/data — domain-scoped persistence repositories.

Each module in this package owns CRUD for exactly one aggregate:

- tone_profile_repo     — creator tone/personality (BOOTSTRAP → Doc D)
- content_chunks_repo   — RAG chunks (INGESTIÓN batch)
- instagram_posts_repo  — raw IG post content lake (INGESTIÓN batch)

See backend/docs/forensic/tone_profile_db/ for the refactor rationale.
Backward-compat imports via core.tone_profile_db still work via re-export.
"""
