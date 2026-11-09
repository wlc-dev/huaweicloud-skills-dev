#!/bin/sh
# fake_hcloud.sh — 离线测试替身：不发任何网络请求，按 FAKE_MODE 输出固定响应
# 用法: FAKE_MODE=ok|page1|page2|empty|403|use_error|broken bash fake_hcloud.sh VPC ListVpcs ...

MODE="${FAKE_MODE:-ok}"

case "$MODE" in
  ok)
    cat <<'JSON'
{"vpcs":[{"id":"vpc-0001","name":"demo-vpc-a","cidr":"192.168.0.0/16","status":"OK","enterprise_project_id":"0","created_at":"2026-01-01T00:00:00Z"},{"id":"vpc-0002","name":"demo-vpc-b","cidr":"10.0.0.0/8","status":"CREATING","enterprise_project_id":"0","created_at":"2026-01-02T00:00:00Z"}],"page_info":{}}
JSON
    exit 0
    ;;
  page1)
    cat <<'JSON'
{"vpcs":[{"id":"vpc-0001","name":"demo-vpc-a","cidr":"192.168.0.0/16","status":"OK"}],"page_info":{"next_marker":"vpc-0001"}}
JSON
    exit 0
    ;;
  page2)
    cat <<'JSON'
{"vpcs":[{"id":"vpc-0002","name":"demo-vpc-b","cidr":"10.0.0.0/8","status":"OK"}],"page_info":{}}
JSON
    exit 0
    ;;
  paging)
    case " $* " in
      *" --marker="*)
        echo '{"vpcs":[{"id":"vpc-0002","name":"demo-vpc-b","cidr":"10.0.0.0/8","status":"OK"}],"page_info":{}}'
        ;;
      *)
        echo '{"vpcs":[{"id":"vpc-0001","name":"demo-vpc-a","cidr":"192.168.0.0/16","status":"OK"}],"page_info":{"next_marker":"vpc-0001"}}'
        ;;
    esac
    exit 0
    ;;
  empty)
    echo '{"vpcs":[],"page_info":{}}'
    exit 0
    ;;
  403)
    echo '{"error_code":"VPC.0002","error_msg":"403 Forbidden: insufficient permission"}'
    exit 1
    ;;
  use_error)
    echo "[USE_ERROR]Invalid parameter: limit" >&2
    exit 0
    ;;
  broken)
    echo '{"vpcs":[{"id":"vpc-0001",'
    exit 1
    ;;
  *)
    echo "fake_hcloud: unknown FAKE_MODE=$MODE" >&2
    exit 2
    ;;
esac