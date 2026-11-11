#!/bin/bash
# install_cli.sh — 手动安装 skill-quality-cli（可选：仅用于匿名质量遥测，不阻塞搜索/安装主流程）。
#
# 合规: 本脚本由用户/agent 主动执行（见 SKILL.md Step 0 / references 指引）;
#       业务脚本不调用本文件。
# 安全(供应链): 固定版本 + SHA256 白名单校验, 未命中白名单一律拒绝安装。
# 可用性语义:
#   · 默认 best-effort —— 当前平台没有可信安装包 / 下载失败 → 打印可读告警并退出 0，
#     因为 search-skills.py 与 npx 安装流程都不依赖该 CLI（它只做匿名遥测）。
#   · --strict —— 安装失败按非零退出（需要 fail-closed 安装语义时使用）。
#   · 校验和不匹配始终退出 1（疑似篡改，任何模式下都拒绝）。
# 用法:
#   bash scripts/install_cli.sh [--strict] [--version V] [--arch ARCH] [--sha256 HASH] [--help]
set -euo pipefail

OBS_BASE="https://obs-skills-repository.obs.cn-north-4.myhuaweicloud.com/skill-quality-cli"

STRICT=0

usage() {
    cat <<'EOF' >&2
用法: bash scripts/install_cli.sh [选项]
  -h, --help            显示本帮助
      --strict          安装失败时返回非零（默认 best-effort，失败仅告警）
  -v, --version VERSION 指定固定版本 (默认: SQCLI_PINNED_VERSION 或 1.1.8)
  -a, --arch ARCH       指定目标架构 (x86_64|arm64, 默认: uname -m)
  -s, --sha256 HASH     指定 tar.gz 的 SHA256 校验和 (白名单外时显式提供)
EOF
}

soft_fail() {
    echo "警告: $*" >&2
    echo "       本技能搜索/安装主流程不依赖 skill-quality-cli（它仅用于匿名遥测），继续执行。" >&2
    if [ "$STRICT" = "1" ]; then
        exit 1
    fi
    exit 0
}

# 解析命名参数 (getopt: 支持长选项; 未传参时保持默认行为)
PARSED=$(getopt -o hv:a:s: --long help,strict,version:,arch:,sha256: -n "$(basename "$0")" -- "$@") || { usage; exit 1; }
eval set -- "$PARSED"

while true; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --strict) STRICT=1; shift ;;
        -v|--version) PINNED_VERSION="$2"; shift 2 ;;
        -a|--arch) ARCH_OVERRIDE="$2"; shift 2 ;;
        -s|--sha256) SHA256_OVERRIDE="$2"; shift 2 ;;
        --) shift; break ;;
        *) usage; exit 1 ;;
    esac
done

# 已安装且可用 → 直接成功
if command -v skill-quality-cli >/dev/null 2>&1 && skill-quality-cli version >/dev/null 2>&1; then
    echo "skill-quality-cli 已可用，无需安装"
    exit 0
fi

# 固定版本 + SHA256 白名单（可信发布渠道 = OBS 官方桶 + 本文件声明的哈希）。
#    VERSION 升级时, 由维护者同步更新 PINNED_VERSION 与对应架构的 SHA256。
PINNED_VERSION="${PINNED_VERSION:-${SQCLI_PINNED_VERSION:-1.1.8}}"
# 官方发布通道当前仅提供 linux-arm64 构建。
PINNED_SHA256_ARM64="1a73773831c0f52542f5591cd9e5126b0c160b8dd36b67f9f833edb0c06a03d5"

ARCH="${ARCH_OVERRIDE:-$(uname -m)}"
case "$ARCH" in
    x86_64|amd64)
        LINUX_ARCH="x86_64"
        if [ -n "${SHA256_OVERRIDE:-}" ]; then
            EXPECTED_SHA256="$SHA256_OVERRIDE"
        elif [ -n "${SQCLI_SHA256_X86_64:-}" ]; then
            EXPECTED_SHA256="$SQCLI_SHA256_X86_64"
        else
            soft_fail "skill-quality-cli 官方发布通道当前仅提供 linux-arm64 构建，x86_64 无法自动安装"
        fi
        ;;
    aarch64|arm64)
        LINUX_ARCH="arm64"
        EXPECTED_SHA256="${SHA256_OVERRIDE:-${SQCLI_SHA256_ARM64:-$PINNED_SHA256_ARM64}}"
        ;;
    *)
        soft_fail "不支持的架构 ${ARCH}"
        ;;
esac

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

PKG_URL="${OBS_BASE}/v${PINNED_VERSION}/skill-quality-cli-v${PINNED_VERSION}-linux-${LINUX_ARCH}.tar.gz"
if ! curl -fsSL --max-time 30 --connect-timeout 5 -o "${TMPDIR}/sqc.tar.gz" "$PKG_URL"; then
    soft_fail "下载 skill-quality-cli 失败(${LINUX_ARCH}): ${PKG_URL}；请检查网络或稍后重试"
fi

# SHA256 校验（不通过 → 拒装, 防供应链投毒；任何模式都非零退出）
GOT_SHA256=$(sha256sum "${TMPDIR}/sqc.tar.gz" | awk '{print $1}')
if [ "$GOT_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "错误: skill-quality-cli 校验和不匹配(期望 ${EXPECTED_SHA256}, 实际 ${GOT_SHA256}), 可能被篡改, 已拒绝安装" >&2
    exit 1
fi

if ! tar xzf "${TMPDIR}/sqc.tar.gz" -C "${TMPDIR}" --no-same-owner 2>/dev/null; then
    soft_fail "解压 skill-quality-cli 安装包失败（安装包可能已损坏）"
fi

mkdir -p ~/.local/bin/skill-quality-cli.d
cp "${TMPDIR}/skill-quality-cli" ~/.local/bin/ 2>/dev/null || true
cp "${TMPDIR}/skill-quality-cli.bin" ~/.local/bin/ 2>/dev/null || true
cp "${TMPDIR}/skill-quality-cli.d/cli_entry.py" ~/.local/bin/skill-quality-cli.d/ 2>/dev/null || true
cp "${TMPDIR}/skill-quality-cli.d/cli_reporting.py" ~/.local/bin/skill-quality-cli.d/ 2>/dev/null || true
chmod +x ~/.local/bin/skill-quality-cli ~/.local/bin/skill-quality-cli.bin 2>/dev/null || true

if ! command -v skill-quality-cli >/dev/null 2>&1; then
    if [ -x "$HOME/.local/bin/skill-quality-cli" ]; then
        echo "skill-quality-cli v${PINNED_VERSION} 已安装到用户级 bin 目录（如需直接调用: 将 ~/.local/bin 加入 PATH）"
        exit 0
    fi
    soft_fail "安装产物缺失或不可执行（${HOME}/.local/bin/skill-quality-cli）"
fi

echo "skill-quality-cli v${PINNED_VERSION} 安装完成（手动触发）"