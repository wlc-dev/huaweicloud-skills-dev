# Acceptance Criteria

## Functional Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-01 | Counts immediate subdirectories of a bucket | `python3 scripts/count_obs_directories.py --bucket <bucket>` prints a single non-negative integer matching `hcloud OBS ls obs://<bucket>/ -d` "Folder number: N" |
| AC-02 | Counts subdirectories under a prefix | `--prefix <prefix>` restricts the count to directories directly under that prefix |
| AC-03 | Recursive counting works | `--recursive` returns the total directory count across all nesting levels |
| AC-04 | Empty bucket returns 0 | A bucket with no objects returns `0` |
| AC-05 | Only the count is returned | Output is a single integer with no surrounding text |
| AC-06 | SDK fallback works | `--executor sdk` returns the same immediate count as the CLI path |
| AC-07 | Read-only guarantee | No create/update/delete operation is invoked by this skill |

## Security Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-S1 | No AK/SK hardcoded in skill files | grep for `AK=`, `SK=`, `access.key=`, `secret.key=` on the skill directory returns nothing |
| AC-S2 | No KooCLI `configure set` credential command | SKILL.md and references never include KooCLI `configure set` with credential flags |
| AC-S3 | Least-privilege IAM policy | `references/iam-policies.md` grants only `obs:bucket:ListBucket` and `obs:object:List` |
| AC-S4 | No cross-skill calls | SKILL.md does not reference other skill names |

## Quality Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-Q1 | SKILL.md follows the Huawei Cloud Skill Specification | `bash scripts/validate-skill.sh <skill-path>` passes with zero Critical failures |
| AC-Q2 | Script runs without syntax errors | `python3 scripts/count_obs_directories.py --help` exits 0 |
| AC-Q3 | SKILL.md <= 500 lines, total files <= 30 | `wc -l SKILL.md` reports line count; `find . -type f` reports file count |
