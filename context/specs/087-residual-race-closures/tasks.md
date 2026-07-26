# 087 — tasks

1. [ ] Redrive rewiring in writes.py: occupant-vanished arms raise
       StaleSnapshot; dir-absorbs-dir unchanged outcome; `_conflict`
       gains retryable=True. Update unit tests that pinned the old
       classifications.
2. [ ] Redrive rewiring in topology.py: move/restore claim and copy
       chunk IntegrityError → StaleSnapshot; delete
       `_classify_claim_race`; update the ghost-blocks-restore and
       address-race pins to the redriven ladder outcomes.
3. [ ] Delete post-claim re-collection with late-arrival byte-budget
       check; transfer verbs get the same late check.
4. [ ] Guarded occupant destroy in _execute_move (version-at-probe
       threaded from the ladder).
5. [ ] Single-row claim helper with the capability gate
       (sane rowcount → RETURNING → unsupported); wire the three call
       sites; insane-rowcount unit test.
6. [ ] Absorb-arm path predicate on both arms + verified application;
       miss → StaleSnapshot.
7. [ ] Race-suite pins: depth-2 delete, overwrite-purge survival
       (move + restore), copy child-collision honesty, ancestor-mint
       storm.
8. [ ] sqlite suite, ruff, ty, coverage to baseline.
9. [ ] Four engine legs green; 10k-batch bench within noise on
       Postgres + MySQL.
