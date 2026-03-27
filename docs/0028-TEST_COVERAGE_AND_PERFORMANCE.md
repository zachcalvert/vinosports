# Test Coverage & Performance

Two back-to-back efforts that transformed the test suite: a coverage push from 59% to 90%, followed by a parallelization overhaul that cut runtime from ~6 minutes to ~30 seconds.

## Coverage: 59% → 90%

PR [#14](https://github.com/zachcalvert/vinosports/pull/14) raised source coverage from 59% to 90% by adding ~780 new tests across all four codebases. The suite grew from 616 to 1,392 tests.

| Suite | Before | After | Change |
|-------|--------|-------|--------|
| vinosports-core | 79 | 124 | +45 |
| hub | 47 | 110 | +63 |
| EPL | 41 | 335 | +294 |
| NBA | 449 | 823 | +374 |
| **Total** | **616** | **1,392** | **+776** |

Coverage gains came from testing views, tasks, services, template tags, and edge cases that were previously untouched. The work followed the same principles as the initial test infrastructure effort (see [0027-TEST_INFRASTRUCTURE.md](0027-TEST_INFRASTRUCTURE.md)): factories over fixtures, behavior over implementation.

## Performance: ~6 min → ~30 sec

With 1,392 tests, the sequential test run took roughly 6 minutes both locally and in CI. Four changes brought that down dramatically:

### 1. pytest-xdist (parallel execution)

Added `pytest-xdist` and run tests with `-n auto`, which spawns one worker per CPU core. Each worker gets its own test database automatically via pytest-django. The existing autouse fixtures (celery eager mode, cache clearing) work correctly across workers with no isolation issues.

### 2. Coverage separated from default run

Previously, `--cov` flags were baked into `addopts` in `pyproject.toml`, meaning every test run paid the ~15-20% coverage overhead. Coverage flags were moved out of `addopts` and into explicit command invocations, so local dev runs skip coverage entirely.

### 3. Database reuse for local dev

Added `--reuse-db` to the local `make test` target. pytest-django skips tearing down and recreating the test database between runs when the schema hasn't changed. First run creates the databases (~78s); subsequent runs reuse them (~31s).

### 4. Makefile targets split

| Command | Flags | Use case |
|---------|-------|----------|
| `make test` | `-n auto --reuse-db` | Fast local development |
| `make test-ci` | `-n auto --cov=...` | CI with coverage reporting |

CI uses `make test-ci` equivalent flags (parallel + coverage, no reuse-db since CI environments are ephemeral).

### Results

| Scenario | Before | After |
|----------|--------|-------|
| CI (GitHub Actions) | ~6 min | ~2-3 min (estimated) |
| Local (first run) | ~6 min | ~78 sec |
| Local (subsequent) | ~6 min | ~31 sec |

## Files Changed

- `pyproject.toml` — Stripped coverage from `addopts`
- `Dockerfile` — Added `pytest-xdist` to pip install
- `Makefile` — Split into `test` (fast) and `test-ci` (coverage) targets
- `.github/workflows/ci.yml` — Added `pytest-xdist`, explicit coverage flags + parallel execution
