# IAM Policies

This skill does not access any Huawei Cloud service. It is a pure local Python
generator that reads a built-in dish library and writes a menu to standard output
or a local file.

- No Huawei Cloud API / SDK / KooCLI calls are made.
- No IAM user, agency, or policy is required.
- No cloud resource is read, created, modified, or deleted.

Therefore no IAM policy document is needed. If this skill is ever extended to read
a cloud-hosted dish library, replace this file with a least-privilege policy that
grants only the required read action.