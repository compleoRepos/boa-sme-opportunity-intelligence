#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command git
require_command jq
require_command npm
require_command python3

RUN_SUFFIX="$(date -u +%Y%m%dT%H%M%SZ)-$$"
WORK_DIR=$(mktemp -d "/tmp/boa-security-scans-${RUN_SUFFIX}.XXXXXX")
VENV_DIR="$WORK_DIR/venv"
HISTORY_REPOSITORY="$WORK_DIR/history-repository"
OUTPUT_FILE=${SECURITY_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/security/RESULTATS-SCANS-SECURITE.json}
GITLEAKS_IMAGE="zricethezav/gitleaks:v8.21.2"
TRIVY_IMAGE="aquasec/trivy:0.58.1"
BACKEND_IMAGE="boa-sme-backend-security:${RUN_SUFFIX}"
FRONTEND_IMAGE="boa-sme-frontend-security:${RUN_SUFFIX}"

mkdir -p "$(dirname -- "$OUTPUT_FILE")"

cleanup() {
  docker_cli image rm --force "$BACKEND_IMAGE" "$FRONTEND_IMAGE" >/dev/null 2>&1 || true
  rm -rf "$PROJECT_ROOT/backend/build"
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

user_flag="$(id -u):$(id -g)"
docker_cli run --rm --user "$user_flag" \
  -v "$PROJECT_ROOT:/repo:ro" -v "$WORK_DIR:/work" \
  "$GITLEAKS_IMAGE" detect --source /repo --no-git \
  --config /repo/.gitleaks.toml --redact \
  --report-format json --report-path /work/gitleaks-worktree.json
git clone --quiet --no-local "$PROJECT_ROOT" "$HISTORY_REPOSITORY"
[[ $(git -C "$HISTORY_REPOSITORY" rev-parse HEAD) == "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" ]]
docker_cli run --rm --user "$user_flag" \
  -v "$HISTORY_REPOSITORY:/history:ro" -v "$PROJECT_ROOT:/config:ro" -v "$WORK_DIR:/work" \
  "$GITLEAKS_IMAGE" detect --source /history \
  --config /config/.gitleaks.toml --redact \
  --report-format json --report-path /work/gitleaks-history.json

worktree_findings=$(jq 'length' "$WORK_DIR/gitleaks-worktree.json")
history_findings=$(jq 'length' "$WORK_DIR/gitleaks-history.json")
[[ "$worktree_findings" -eq 0 ]]
[[ "$history_findings" -eq 0 ]]
# Gitleaks scans every reachable ref in the autonomous clone and reports
# non-merge commits in its "commits scanned" counter.
history_commits=$(git -C "$HISTORY_REPOSITORY" rev-list --all --no-merges --count)

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check --quiet pip-audit "$PROJECT_ROOT/backend"
"$VENV_DIR/bin/python" -m pip freeze \
  | grep -v '^boa-sme-opportunity-intelligence' >"$WORK_DIR/audit-requirements.txt"
"$VENV_DIR/bin/pip-audit" --requirement "$WORK_DIR/audit-requirements.txt" \
  --format json --output "$WORK_DIR/pip-audit.json"
python_dependencies=$(jq '.dependencies | length' "$WORK_DIR/pip-audit.json")
python_vulnerabilities=$(jq '[.dependencies[].vulns[]?] | length' "$WORK_DIR/pip-audit.json")
[[ "$python_vulnerabilities" -eq 0 ]]

(
  cd "$PROJECT_ROOT/frontend"
  npm audit --audit-level=high --json >"$WORK_DIR/npm-audit.json"
)
npm_dependencies=$(jq '.metadata.dependencies.total' "$WORK_DIR/npm-audit.json")
npm_info=$(jq '.metadata.vulnerabilities.info' "$WORK_DIR/npm-audit.json")
npm_low=$(jq '.metadata.vulnerabilities.low' "$WORK_DIR/npm-audit.json")
npm_moderate=$(jq '.metadata.vulnerabilities.moderate' "$WORK_DIR/npm-audit.json")
npm_high=$(jq '.metadata.vulnerabilities.high' "$WORK_DIR/npm-audit.json")
npm_critical=$(jq '.metadata.vulnerabilities.critical' "$WORK_DIR/npm-audit.json")
[[ "$npm_high" -eq 0 ]]
[[ "$npm_critical" -eq 0 ]]

docker_cli build --file "$PROJECT_ROOT/infrastructure/docker/backend.Dockerfile" \
  --tag "$BACKEND_IMAGE" "$PROJECT_ROOT" >"$WORK_DIR/backend-build.log" 2>&1
docker_cli build --file "$PROJECT_ROOT/infrastructure/docker/frontend.Dockerfile" \
  --tag "$FRONTEND_IMAGE" "$PROJECT_ROOT" >"$WORK_DIR/frontend-build.log" 2>&1

for target in backend frontend; do
  image_var="${target^^}_IMAGE"
  image=${!image_var}
  docker_cli run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock -v "$WORK_DIR:/work" \
    "$TRIVY_IMAGE" image --quiet --severity HIGH,CRITICAL \
    --format json --output "/work/trivy-${target}.json" "$image"
done

backend_high=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$WORK_DIR/trivy-backend.json")
backend_critical=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$WORK_DIR/trivy-backend.json")
frontend_high=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$WORK_DIR/trivy-frontend.json")
frontend_critical=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$WORK_DIR/trivy-frontend.json")
backend_with_fix=$(jq '[.Results[]?.Vulnerabilities[]? | select((.Severity == "HIGH" or .Severity == "CRITICAL") and (.FixedVersion // "") != "")] | length' "$WORK_DIR/trivy-backend.json")
backend_without_fix=$(jq '[.Results[]?.Vulnerabilities[]? | select((.Severity == "HIGH" or .Severity == "CRITICAL") and (.FixedVersion // "") == "")] | length' "$WORK_DIR/trivy-backend.json")
frontend_with_fix=$(jq '[.Results[]?.Vulnerabilities[]? | select((.Severity == "HIGH" or .Severity == "CRITICAL") and (.FixedVersion // "") != "")] | length' "$WORK_DIR/trivy-frontend.json")
frontend_without_fix=$(jq '[.Results[]?.Vulnerabilities[]? | select((.Severity == "HIGH" or .Severity == "CRITICAL") and (.FixedVersion // "") == "")] | length' "$WORK_DIR/trivy-frontend.json")
backend_os_family=$(jq -r '.Metadata.OS.Family // "unknown"' "$WORK_DIR/trivy-backend.json")
backend_os_name=$(jq -r '.Metadata.OS.Name // "unknown"' "$WORK_DIR/trivy-backend.json")
frontend_os_family=$(jq -r '.Metadata.OS.Family // "unknown"' "$WORK_DIR/trivy-frontend.json")
frontend_os_name=$(jq -r '.Metadata.OS.Name // "unknown"' "$WORK_DIR/trivy-frontend.json")
printf '[security-scans] application images: backend HIGH=%s CRITICAL=%s withFix=%s withoutFix=%s; frontend HIGH=%s CRITICAL=%s withFix=%s withoutFix=%s\n' \
  "$backend_high" "$backend_critical" "$backend_with_fix" "$backend_without_fix" \
  "$frontend_high" "$frontend_critical" "$frontend_with_fix" "$frontend_without_fix"
[[ "$backend_with_fix" -eq 0 ]]
[[ "$frontend_with_fix" -eq 0 ]]

external_images_json="$WORK_DIR/external-images.jsonl"
external_high=0
external_critical=0
external_with_fix=0
external_without_fix=0
external_image_count=0
while read -r image; do
  [[ "$image" == *@sha256:* ]]
  external_image_count=$((external_image_count + 1))
  report="trivy-external-${external_image_count}.json"
  docker_cli pull "$image" >/dev/null
  docker_cli run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock -v "$WORK_DIR:/work" \
    "$TRIVY_IMAGE" image --quiet --severity HIGH,CRITICAL \
    --format json --output "/work/${report}" "$image"
  high=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' "$WORK_DIR/$report")
  critical=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' "$WORK_DIR/$report")
  with_fix=$(jq '[.Results[]?.Vulnerabilities[]? | select((.Severity == "HIGH" or .Severity == "CRITICAL") and (.FixedVersion // "") != "")] | length' "$WORK_DIR/$report")
  without_fix=$(jq '[.Results[]?.Vulnerabilities[]? | select((.Severity == "HIGH" or .Severity == "CRITICAL") and (.FixedVersion // "") == "")] | length' "$WORK_DIR/$report")
  os_family=$(jq -r '.Metadata.OS.Family // "unknown"' "$WORK_DIR/$report")
  os_name=$(jq -r '.Metadata.OS.Name // "unknown"' "$WORK_DIR/$report")
  external_high=$((external_high + high))
  external_critical=$((external_critical + critical))
  external_with_fix=$((external_with_fix + with_fix))
  external_without_fix=$((external_without_fix + without_fix))
  jq -cn \
    --arg image "$image" --arg osFamily "$os_family" --arg osName "$os_name" \
    --argjson high "$high" --argjson critical "$critical" \
    --argjson withFix "$with_fix" --argjson withoutFix "$without_fix" \
    '{image:$image,osFamily:$osFamily,osName:$osName,high:$high,critical:$critical,withUpstreamFix:$withFix,withoutUpstreamFix:$withoutFix}' \
    >>"$external_images_json"
done < <(awk '/^[[:space:]]+image:/ {print $2}' "$PROJECT_ROOT/infrastructure/docker-compose.yml")
printf '[security-scans] external images: count=%s HIGH=%s CRITICAL=%s withFix=%s withoutFix=%s\n' \
  "$external_image_count" "$external_high" "$external_critical" "$external_with_fix" "$external_without_fix"
[[ "$external_image_count" -eq 3 ]]
external_images=$(jq -s '.' "$external_images_json")
total_high=$((backend_high + frontend_high + external_high))
total_critical=$((backend_critical + frontend_critical + external_critical))
if [[ "$total_high" -eq 0 && "$total_critical" -eq 0 ]]; then
  image_release_gate="READY"
  image_scan_check="PASS"
else
  image_release_gate="BLOCKED_IMAGE_CVES"
  image_scan_check="BLOCKED"
fi

base_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
source_digest=$(
  cd "$PROJECT_ROOT"
  sha256sum \
    .gitleaks.toml \
    backend/pyproject.toml \
    frontend/package-lock.json \
    infrastructure/docker-compose.yml \
    infrastructure/docker/backend.Dockerfile \
    infrastructure/docker/frontend.Dockerfile \
    scripts/common.sh \
    scripts/validate-security-scans.sh \
    | sha256sum | awk '{print $1}'
)
generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
run_id="security-scans-${RUN_SUFFIX}"
backend_base_image=$(awk '/^FROM / {print $2; exit}' "$PROJECT_ROOT/infrastructure/docker/backend.Dockerfile")
frontend_build_image=$(awk '/^FROM / {print $2; exit}' "$PROJECT_ROOT/infrastructure/docker/frontend.Dockerfile")
frontend_runtime_image=$(awk '/^FROM / {image=$2} END {print image}' "$PROJECT_ROOT/infrastructure/docker/frontend.Dockerfile")

jq -n \
  --arg runId "$run_id" \
  --arg generatedAt "$generated_at" \
  --arg baseCommit "$base_commit" \
  --arg sourceDigest "$source_digest" \
  --arg gitleaksImage "$GITLEAKS_IMAGE" \
  --arg trivyImage "$TRIVY_IMAGE" \
  --arg backendBaseImage "$backend_base_image" \
  --arg frontendBuildImage "$frontend_build_image" \
  --arg frontendRuntimeImage "$frontend_runtime_image" \
  --arg backendOsFamily "$backend_os_family" \
  --arg backendOsName "$backend_os_name" \
  --arg frontendOsFamily "$frontend_os_family" \
  --arg frontendOsName "$frontend_os_name" \
  --arg imageReleaseGate "$image_release_gate" \
  --arg imageScanCheck "$image_scan_check" \
  --argjson historyCommits "$history_commits" \
  --argjson worktreeFindings "$worktree_findings" \
  --argjson historyFindings "$history_findings" \
  --argjson pythonDependencies "$python_dependencies" \
  --argjson pythonVulnerabilities "$python_vulnerabilities" \
  --argjson npmDependencies "$npm_dependencies" \
  --argjson npmInfo "$npm_info" \
  --argjson npmLow "$npm_low" \
  --argjson npmModerate "$npm_moderate" \
  --argjson npmHigh "$npm_high" \
  --argjson npmCritical "$npm_critical" \
  --argjson backendHigh "$backend_high" \
  --argjson backendCritical "$backend_critical" \
  --argjson backendWithFix "$backend_with_fix" \
  --argjson backendWithoutFix "$backend_without_fix" \
  --argjson frontendHigh "$frontend_high" \
  --argjson frontendCritical "$frontend_critical" \
  --argjson frontendWithFix "$frontend_with_fix" \
  --argjson frontendWithoutFix "$frontend_without_fix" \
  --argjson externalImages "$external_images" \
  --argjson externalHigh "$external_high" \
  --argjson externalCritical "$external_critical" \
  --argjson externalWithFix "$external_with_fix" \
  --argjson externalWithoutFix "$external_without_fix" \
  '{runId:$runId,generatedAt:$generatedAt,status:(if $imageReleaseGate == "READY" then "PASS" else "BLOCKED" end),scanExecutionStatus:"PASS",releaseStatus:$imageReleaseGate,scope:"LOCAL_SYNTHETIC_SECURITY_SCANS",sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest,digestScope:"security",digestManifest:"SOURCE-MANIFEST-FI.json",digestAlgorithm:"SHA-256 of the explicit ordered security input list"},tools:{gitleaks:$gitleaksImage,trivy:$trivyImage},secrets:{worktreeFindings:$worktreeFindings,historyCommits:$historyCommits,historyFindings:$historyFindings},dependencies:{python:{audited:$pythonDependencies,knownVulnerabilities:$pythonVulnerabilities},frontend:{audited:$npmDependencies,info:$npmInfo,low:$npmLow,moderate:$npmModerate,high:$npmHigh,critical:$npmCritical}},images:{application:{backend:{baseImage:$backendBaseImage,osFamily:$backendOsFamily,osName:$backendOsName,high:$backendHigh,critical:$backendCritical,withUpstreamFix:$backendWithFix,withoutUpstreamFix:$backendWithoutFix},frontend:{buildImage:$frontendBuildImage,runtimeImage:$frontendRuntimeImage,osFamily:$frontendOsFamily,osName:$frontendOsName,high:$frontendHigh,critical:$frontendCritical,withUpstreamFix:$frontendWithFix,withoutUpstreamFix:$frontendWithoutFix}},external:{items:$externalImages,summary:{high:$externalHigh,critical:$externalCritical,withUpstreamFix:$externalWithFix,withoutUpstreamFix:$externalWithoutFix}}},checks:{gitleaksWorktree:"PASS",gitleaksHistory:"PASS",pipAudit:"PASS",npmHighCritical:"PASS",trivyApplicationImagesNoKnownUpstreamFix:"PASS",externalImagesPinnedAndScanned:"PASS",releaseImageGate:$imageScanCheck},limitations:["Les bases de vulnérabilités reflètent leur état au moment du run et doivent être rescannées régulièrement.","Toutes les CVE HIGH/CRITICAL detectees sont visibles et bloquent le statut release; aucune exclusion --ignore-unfixed n est appliquee. Un FixedVersion Trivy indique une correction de composant connue, pas necessairement un digest d image amont deja publie et valide.","Deux avis MODERATE concernent Vitest, dépendance de développement; ils ne sont pas masqués et restent une dette à traiter.","Ces scans automatisés ne remplacent ni pentest, ni revue de configuration de la cible BOA, ni analyse de menace, ni signature/SBOM des artefacts publies."]}' >"$OUTPUT_FILE"

echo "[security-scans] scanExecution=PASS releaseStatus=$image_release_gate: $OUTPUT_FILE"
