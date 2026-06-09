# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-09

### Added

- Clean architecture implementation with domain models, sync plan use cases, and isolated ports/adapters.
- PostgreSQL repository implementation with robust environment validation.
- Structured logging system for domain events.
- Automated GitHub Actions pipeline for CI/CD, including `uv` dependency management and strict code formatting (`ruff`, `mypy`).

### Fixed

- Implemented JIT dynamic IP whitelisting to allow GitHub Actions runners to securely connect to the Supabase database.
