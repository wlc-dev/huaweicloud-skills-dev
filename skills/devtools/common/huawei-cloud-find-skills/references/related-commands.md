# Related Commands Quick Reference - huawei-cloud-skill-creator-skill

> **Note**: this reference is inherited from the `huawei-cloud-skill-creator` toolchain. The `scripts/validate-skill.sh` / `scripts/test-cli-commands.sh` / `scripts/generate-dataflow-diagram.sh` commands below are provided by that skill and are run from its directory, not from `huawei-cloud-find-skills` (whose only script is `scripts/search-skills.py` plus `scripts/install_cli.sh`).

> Read this file when you need to quickly look up Skill creation related commands.

## hcloud CLI General Commands

Use CLI help flags to explore services and operations (e.g., `--help`).

```bash
# Example: list ECS instances
hcloud ECS ListServers --cli-region={region}
```

## Common Service Quick Reference

| Service | Common Operations | Description |
|---------|-------------------|-------------|
| ECS | ListServers, ShowServer, CreateServers, DeleteServers | Elastic Cloud Server |
| VPC | ListVpcs, ShowVpc, CreateVpc, DeleteVpc | Virtual Private Cloud |
| OBS | ListBuckets, CreateBucket, DeleteBucket | Object Storage |
| RDS | ListInstances, ShowInstance, CreateInstance | Relational Database |
| IAM | ListUsers, ShowUser, CreatePolicy | Identity & Access Mgmt |
| CCE | ListClusters, ShowCluster, CreateCluster | Cloud Container Engine |
| CES | ListMetrics, ShowMetricData, ListAlarms | Cloud Eye |
| ELB | ListLoadBalancers, ShowLoadBalancer | Elastic Load Balancer |
| EVS | ListVolumes, ShowVolume, CreateVolume | Elastic Volume |

## Skill Validation Commands

```bash
# Validate Skill structure
bash scripts/validate-skill.sh {skill-path}

# Check SKILL.md format
head -1 {skill-path}/SKILL.md  # Should be ---

# Check references completeness
ls {skill-path}/references/
```

## File Operations

```bash
# Create Skill directory structure
mkdir -p {domain}/{skill-name}/{references,scripts,templates,demo}

# Generate SKILL.md from template
cp templates/SKILL.md.template {domain}/{skill-name}/SKILL.md
```
