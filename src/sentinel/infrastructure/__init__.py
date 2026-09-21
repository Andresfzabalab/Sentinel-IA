"""Every concrete adapter. The only place third-party infrastructure
libraries (GitHub SDK/HTTP client, sqlite3, an AI provider's SDK, a
scanner's CLI wrapper) are imported. May import from any module's domain/
and ports/; nothing in domain/ or application/ imports back from here
(dependency inversion, enforced by directory structure).
"""
