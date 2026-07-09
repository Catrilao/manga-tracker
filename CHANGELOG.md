# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0](https://github.com/Catrilao/manga-tracker/compare/v1.2.0...v1.3.0) (2026-07-09)


### Features

* **observability:** implement active telemetry, http status tracking ([fb77957](https://github.com/Catrilao/manga-tracker/commit/fb77957296b5943a1d210e274d3f21998b70ff8a))


### Bug Fixes

* **core:** safely extract status code from domain exceptions ([35a8938](https://github.com/Catrilao/manga-tracker/commit/35a8938fce33c13fb7ad7ce8176247a1718ba9e2))
* **core:** skip mangas without sources ([acc5adf](https://github.com/Catrilao/manga-tracker/commit/acc5adf794cd6a69d76c3c910baa08a10d2287b4))
* **scraper:** add a User-Agent header to the MangaDex requests ([dbfb540](https://github.com/Catrilao/manga-tracker/commit/dbfb540eb92db54980108417571472126ad18784))

## [1.2.0](https://github.com/Catrilao/manga-tracker/compare/v1.1.0...v1.2.0) (2026-06-29)


### Features

* **core:** unify scraper strategy and consolidate database ([#15](https://github.com/Catrilao/manga-tracker/issues/15)) ([8445c37](https://github.com/Catrilao/manga-tracker/commit/8445c3749f0205b39edb43a5bb1a0d514963dc0f))

## [1.1.0](https://github.com/Catrilao/manga-tracker/compare/v1.0.0...v1.1.0) (2026-06-09)


### Features

* **audit:** add scrape run auditing and persistence ([8fd4b37](https://github.com/Catrilao/manga-tracker/commit/8fd4b37fec0f466d9eb5aa5247cee9e60303f3d9))

## [1.0.0] - 2026-06-09

### Added

- Clean architecture implementation with domain models, sync plan use cases, and isolated ports/adapters.
- PostgreSQL repository implementation with robust environment validation.
- Structured logging system for domain events.
- Automated GitHub Actions pipeline for CI/CD, including `uv` dependency management and strict code formatting (`ruff`, `mypy`).

### Fixed

- Implemented JIT dynamic IP whitelisting to allow GitHub Actions runners to securely connect to the Supabase database.
