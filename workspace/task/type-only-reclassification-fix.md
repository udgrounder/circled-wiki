# Same-path Bundle type reclassification

- Request: the user reported a reproduced `report -> reference` failure, reviewed the diagnosis, and explicitly approved the fix, independent review, commit, new release and deployment to campingtalk-wiki.
- Classification: product defect; preview and apply disagree when classification changes without a path change.
- Input: direct user report and isolated reproduction against installed v1-65d68aa27079. No operational Issue file was found in the local installation, and no operational file was moved or modified for intake.
- Scope: distinguish semantic classification changes from path moves; preserve approval, revision, identity, Evidence, body, history, Validator and rollback behavior. Keep the duplicate recovery same-type restriction.
- Verification: add same-path draft/active, alias-root, no-op, approval, stale revision, exact-byte rollback, existing destination collision and legacy path-only movement regressions.
- Operational boundary: deployment updates managed Runtime assets only. Existing Bundle reclassification, pending Review application and duplicate cleanup are separate operational changes.
- Independent review: `type_only_review` passed the 12 new regressions and all 426 tests; Validator validated=15 invalid=0; diff check passed. The review also reproduced the old failure and found a symlink escape, which was blocked and covered by two no-write regressions.
- Status: source implementation verified; commit, release and installation verification next.
