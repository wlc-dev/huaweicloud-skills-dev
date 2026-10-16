# Verification Method

This skill provides two independent ways to count OBS directories: the KooCLI obsutil-backed command (primary) and the `huaweicloudsdkobs` Python SDK (fallback).

## Verification Script

Run the bundled test script from the skill directory:

```bash
bash scripts/test-cli-commands.sh <skill-path>
```

The script requires a real OBS bucket name via the `TEST_OBS_BUCKET` environment variable (defaults to `obs-hd-dev-static` if unset).

## Manual Verification Steps

1. **Prerequisite check** — confirm hcloud and obsutil are available:

   ```bash
   hcloud version
   hcloud OBS ls -s -limit=1
   ```

   If the second command returns `Please set ak, sk and endpoint in the configuration file!`, obsutil credentials are not configured.

2. **Immediate directory count (CLI primary)**:

   ```bash
   python3 scripts/count_obs_directories.py --bucket <bucket_name>
   ```

   Expected: a single integer. Cross-check with:

   ```bash
   hcloud OBS ls obs://<bucket_name>/ -d
   ```

   The `Folder number: N` line must equal the script output.

3. **Count under a prefix**:

   ```bash
   python3 scripts/count_obs_directories.py --bucket <bucket_name> --prefix <prefix>
   ```

4. **Recursive count**:

   ```bash
   python3 scripts/count_obs_directories.py --bucket <bucket_name> --recursive
   ```

   Expected: an integer >= the immediate count.

5. **SDK fallback** — verify the SDK path returns the same immediate count:

   ```bash
   python3 scripts/count_obs_directories.py --bucket <bucket_name> --executor sdk
   ```

6. **Empty bucket** — a bucket with no objects returns `0`.

7. **Nonexistent bucket** — the script exits non-zero and prints a clear Chinese hint on stderr
   (`错误：指定的 OBS 桶不存在，或当前 AK/SK 无权访问该桶（NoSuchBucket）`):

   ```bash
   python3 scripts/count_obs_directories.py --bucket <nonexistent_bucket>
   ```

   Expected: exit code 1, stderr contains the Chinese NoSuchBucket hint, stdout stays empty.

8. **Missing credentials** — run without AK/SK env vars:

   ```bash
   env -u HUAWEI_ACCESS_KEY -u HUAWEI_SECRET_KEY \
     python3 scripts/count_obs_directories.py --bucket <bucket_name> --executor sdk
   ```

   Expected: exit code 1, stderr contains the Chinese credential hint with configuration guidance.

## Pass Criteria

- The CLI and SDK paths return the same immediate directory count for the same bucket
- The output is a single integer with no surrounding text
- No create/update/delete operation is ever performed
- Error paths (nonexistent bucket, invalid/missing credentials) exit non-zero with a clear Chinese hint on stderr
