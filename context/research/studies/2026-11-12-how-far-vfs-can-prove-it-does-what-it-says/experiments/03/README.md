Experiments for researcher 03, run 2026-11-12 in /private/tmp/claude-501/verif-03 (outside the checkout).

scorecard-local.txt: OpenSSF Scorecard v5.6.0 release binary, `scorecard --local=.` over `git archive HEAD` of vfs at 3ea2465e. Local mode runs 11 of 18 checks; the Vulnerabilities check sends lockfile package names and versions to osv.dev.
lockfile-audit-by-audience.txt: pip-audit over `uv export` of uv.lock split three ways (core runtime, runtime with all extras, dev group), to see which audience the Scorecard Vulnerabilities count falls on.
pypi-provenance.txt and check_pypi_provenance.py: whether the newest release of well-known projects carries a PEP 740 provenance object on PyPI (first file of the release only), via PyPI's public integrity API.
pep740-verify.txt: pypi-attestations 0.0.31 verifying a real attestation, then the same file against a wrong repository.
reproducible-build.sh and reproducible-build.txt: maturin 1.16.0 building the vfs wheel twice from two copies of HEAD at different paths with SOURCE_DATE_EPOCH set, on one macOS arm64 machine, then comparing.
