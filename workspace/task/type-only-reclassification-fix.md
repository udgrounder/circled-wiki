# Same-path Bundle type reclassification

- Request: the user reported a reproduced `report -> reference` failure, reviewed the diagnosis, and explicitly approved the fix, independent review, commit, new release and deployment to campingtalk-wiki.
- Classification: product defect; preview and apply disagree when classification changes without a path change.
- Input: direct user report and isolated reproduction against installed v1-65d68aa27079. No operational Issue file was found in the local installation, and no operational file was moved or modified for intake.
- Scope: distinguish semantic classification changes from path moves; preserve approval, revision, identity, Evidence, body, history, Validator and rollback behavior. Keep the duplicate recovery same-type restriction.
- Verification: add same-path draft/active, alias-root, no-op, approval, stale revision, exact-byte rollback, existing destination collision and legacy path-only movement regressions.
- Operational boundary: deployment updates managed Runtime assets only. Existing Bundle reclassification, pending Review application and duplicate cleanup are separate operational changes.
- Independent review: `type_only_review` passed the 12 new regressions and all 426 tests; Validator validated=15 invalid=0; diff check passed. The review also reproduced the old failure and found a symlink escape, which was blocked and covered by two no-write regressions.
- Product change commit: `6f0b1127fa3a2e7d01ba62496ce8b0ad4abcbb37`; release `v1-641590a89872`, prepared from a clean committed worktree and recorded before deployment.
- Installation verification: `type_only_review` independently verified 106 managed checksums, the full 138-file backup, Validator validated=2459 invalid=0 and 35 installed-Runtime regressions (12 same-path, 1 existing path move, 17 duplicate recovery, 5 batch duplicate prevention). All operational Knowledge, Workspace, local config and entrypoints were preserved.
- Receipts: `workspace/receipts/deployments/campingtalk-wiki/v1-641590a89872.json` and `workspace/receipts/verifications/campingtalk-wiki/v1-641590a89872.json`; detailed preservation evidence is stored alongside the Deployment Receipt.
- Status: complete for the approved product fix, commit, release and deployment. Existing operational Bundle reclassification, Review application and duplicate cleanup were not performed.
