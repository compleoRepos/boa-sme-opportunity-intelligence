#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
require_command curl
require_command jq
require_command sha256sum
require_command file
load_local_env

OUTPUT_DIR=${ML_STUDIO_OUTPUT_DIR:-$PROJECT_ROOT/docs/evidence/ml}
OUTPUT_FILE="$OUTPUT_DIR/RESULTATS-STUDIO-ML.json"
PLAYWRIGHT_FILE="$OUTPUT_DIR/RESULTATS-PLAYWRIGHT-STUDIO-ML.json"
RAW_PLAYWRIGHT=$(mktemp)
trap 'rm -f "$RAW_PLAYWRIGHT"' EXIT
mkdir -p "$OUTPUT_DIR"
RUN_ID="ml-studio-$(date -u +%Y%m%dT%H%M%SZ)-$$"

sql() {
  compose exec -T postgres psql \
    --username "${POSTGRES_ADMIN_USER:-boa_admin}" \
    --dbname "${POSTGRES_DB:-boa_sme}" \
    --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command "$1"
}

printf '[1/7] Qualité backend et frontend\n'
ruff format --check backend/src database tests/unit scripts/*.py >/tmp/boa-ml-studio-ruff-format.log
ruff check backend/src database tests/unit scripts/*.py >/tmp/boa-ml-studio-ruff-check.log
mypy backend >/tmp/boa-ml-studio-mypy.log
APP_ENV=test PYTHONPATH=backend/src:. backend/.venv/bin/pytest tests/unit -q --disable-warnings >/tmp/boa-ml-studio-pytest.log
(
  cd frontend
  npm run typecheck >/tmp/boa-ml-studio-typecheck.log
  npm test -- --run >/tmp/boa-ml-studio-vitest.log
  npm run build >/tmp/boa-ml-studio-build.log
)
shellcheck -x -e SC1091 scripts/*.sh

printf '[2/7] Migrations PostgreSQL combinées\n'
./scripts/validate-ml-studio-postgres.sh >/tmp/boa-ml-studio-migration.log

printf '[3/7] Services Docker et seed synthétique\n'
compose down --volumes --remove-orphans
compose up -d postgres keycloak
wait_for_healthy postgres 180
wait_for_healthy keycloak 180
COMPOSE_PARALLEL_LIMIT=1 compose --profile tools build >/tmp/boa-ml-studio-compose-build.log
./scripts/seed.sh >/tmp/boa-ml-studio-seed.log
compose up -d
for service in analytics signal feature-store rule-engine product ml-engine opportunity api-gateway; do
  wait_for_healthy "$service" 300
done
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:3000 >/dev/null; then break; fi
  sleep 1
done
curl -fsS http://localhost:3000 >/dev/null
compose ps --status running --services | grep -qx 'notification-worker'

printf '[4/7] Pipeline synthétique complet avec observations ML shadow\n'
CUSTOMER_REF=${ML_STUDIO_CUSTOMER_REF:-SME-00035}
AS_OF_DATE=${ML_STUDIO_AS_OF_DATE:-2026-09-30}
CORRELATION_ID="$RUN_ID-pipeline" \
PIPELINE_CUSTOMER_COUNT=${ML_STUDIO_PIPELINE_CUSTOMER_COUNT:-500} \
PIPELINE_BATCH_SIZE=${ML_STUDIO_PIPELINE_BATCH_SIZE:-25} \
AS_OF_DATE="$AS_OF_DATE" \
  ./scripts/run-pipeline.sh >/tmp/boa-ml-studio-pipeline.log

printf '[5/7] Parcours Playwright Karim, Nadia et administrateur\n'
(
  cd tests/e2e
  [[ -x node_modules/.bin/playwright ]] || npm ci >/tmp/boa-ml-studio-e2e-install.log
  timeout --signal=TERM 30m ./node_modules/.bin/playwright test --config playwright.config.ts --reporter=json >"$RAW_PLAYWRIGHT"
)
jq '{
  generatedAt:(now|todateiso8601),
  status:(if .stats.unexpected == 0 and .stats.expected > 0 then "PASS" else "FAIL" end),
  stats:.stats,
  cases:[.. | objects | select(has("file") and has("title") and has("tests")) | {title,file,ok,results:[.tests[].results[-1] | {status,duration}]}]
}' "$RAW_PLAYWRIGHT" >"$PLAYWRIGHT_FILE"
jq -e '.status=="PASS" and .stats.expected>=20 and .stats.unexpected==0' "$PLAYWRIGHT_FILE" >/dev/null

printf '[6/7] Oracles SQL, runtime et captures\n'
training_jobs_succeeded=$(sql "SELECT count(*) FROM ml.training_jobs WHERE status='SUCCEEDED' AND percentage=100;")
latest_training_job=$(sql "SELECT json_build_object('id',id,'manifestId',manifest_id,'algorithm',algorithm,'seed',seed,'status',status,'percentage',percentage,'currentStep',current_step,'steps',steps_json,'result',result_json,'author',author,'correlationId',correlation_id,'createdAt',created_at,'startedAt',started_at,'completedAt',completed_at,'updatedAt',updated_at)::text FROM ml.training_jobs ORDER BY created_at DESC LIMIT 1;")
demo_models=$(sql "SELECT count(*) FROM ml.model_registry WHERE status='DEMO_ONLY';")
simulation_events=$(sql "SELECT count(*) FROM opportunity.scoring_policy_audit_logs WHERE action='SIMULATED' AND new_value_json::jsonb ? 'simulation';")
simulation_sample_count=$(sql "SELECT COALESCE((new_value_json::jsonb #>> '{simulation,sampleCount}')::int,0) FROM opportunity.scoring_policy_audit_logs WHERE action='SIMULATED' AND new_value_json::jsonb ? 'simulation' ORDER BY timestamp DESC LIMIT 1;")
latest_simulation=$(sql "SELECT new_value_json::jsonb->'simulation' FROM opportunity.scoring_policy_audit_logs WHERE action='SIMULATED' AND new_value_json::jsonb ? 'simulation' ORDER BY timestamp DESC LIMIT 1;")
submitted_events=$(sql "SELECT count(*) FROM opportunity.scoring_policy_audit_logs WHERE action='SUBMITTED';")
approved_events=$(sql "SELECT count(*) FROM opportunity.scoring_policy_audit_logs WHERE action='APPROVED';")
published_events=$(sql "SELECT count(*) FROM opportunity.scoring_policy_audit_logs WHERE action='PUBLISHED';")
active_non_rules_only=$(sql "SELECT count(*) FROM opportunity.scoring_policy_versions WHERE status='ACTIVE' AND (rules_weight<>1 OR ml_weight<>0 OR operational_mode<>'RULES_ONLY');")
shadow_opportunities=$(sql "SELECT count(*) FROM opportunity.opportunities WHERE status IN ('OPEN','ACCEPTED','CONTACTED') AND explanation_json::jsonb #>> '{propensityShadow,deploymentMode}'='POC_SHADOW' AND rules_weight=1 AND ml_weight=0;")
alembic_head=$(compose --profile tools run --rm --no-deps --entrypoint /bin/sh migrations -lc 'cd /app/database && alembic -c alembic.ini current' | tail -1 | tr -d '\r')
sklearn_version=$(compose exec -T ml-engine python -c 'import sklearn; print(sklearn.__version__)' | tr -d '\r')
screenshot_count=$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'STUDIO-ML-*.png' | wc -l | tr -d ' ')
invalid_screenshots=$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'STUDIO-ML-*.png' -exec file {} \; | grep -vc 'PNG image data, 1440 x 900,' || true)

[[ "$training_jobs_succeeded" -ge 1 ]]
jq -e '.status=="SUCCEEDED" and .percentage==100 and .startedAt!=null and .completedAt!=null' <<<"$latest_training_job" >/dev/null
[[ "$demo_models" -ge 1 ]]
[[ "$simulation_events" -ge 1 ]]
[[ "$simulation_sample_count" -ge 1 ]]
[[ "$submitted_events" -ge 1 && "$approved_events" -ge 1 && "$published_events" -ge 1 ]]
[[ "$active_non_rules_only" == "0" ]]
[[ "$shadow_opportunities" -ge 1 ]]
[[ "$sklearn_version" == "1.5.2" ]]
[[ "$screenshot_count" -eq 7 && "$invalid_screenshots" -eq 0 ]]
[[ "$alembic_head" == *"0019_ml_studio_catalog_merge"* ]]

pytest_count=$(grep -Eo '[0-9]+ passed' /tmp/boa-ml-studio-pytest.log | tail -1 | awk '{print $1}')
vitest_count=$(grep -E 'Tests  ' /tmp/boa-ml-studio-vitest.log | tail -1 | grep -Eo '[0-9]+ passed' | awk '{print $1}')
playwright_count=$(jq -r '.stats.expected' "$PLAYWRIGHT_FILE")
source_digest=$(sha256sum \
  backend/src/boa_oi/ml_training/service.py \
  backend/src/boa_oi/scoring_policy/routes.py \
  frontend/src/features/ml-studio/MlStudioPage.tsx \
  infrastructure/docker/backend.Dockerfile \
  tests/e2e/ml-studio.spec.ts \
  scripts/validate-ml-studio.sh | sha256sum | awk '{print $1}')

printf '[7/7] Artefact JSON final\n'
jq -n \
  --arg runId "$RUN_ID" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg baseCommit "$(git rev-parse HEAD)" \
  --arg sourceDigest "$source_digest" \
  --arg alembicHead "$alembic_head" \
  --arg sklearnVersion "$sklearn_version" \
  --arg customerRef "$CUSTOMER_REF" \
  --argjson pytestCount "$pytest_count" \
  --argjson vitestCount "$vitest_count" \
  --argjson playwrightCount "$playwright_count" \
  --argjson trainingJobs "$training_jobs_succeeded" \
  --argjson latestTrainingJob "$latest_training_job" \
  --argjson demoModels "$demo_models" \
  --argjson simulationEvents "$simulation_events" \
  --argjson simulationSampleCount "$simulation_sample_count" \
  --argjson latestSimulation "$latest_simulation" \
  --argjson submittedEvents "$submitted_events" \
  --argjson approvedEvents "$approved_events" \
  --argjson publishedEvents "$published_events" \
  --argjson shadowOpportunities "$shadow_opportunities" \
  --argjson screenshots "$screenshot_count" \
  '{
    runId:$runId,
    generatedAt:$generatedAt,
    status:"PASS",
    releaseStatus:"BLOCKED",
    sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest},
    environment:{runtime:"Docker Compose local",cpuOnly:true,llm:false,gpu:false,aws:false,python:"3.12",framework:"scikit-learn",frameworkVersion:$sklearnVersion,alembicHead:$alembicHead},
    gates:{ruff:"PASS",mypy:"PASS",pytest:{status:"PASS",tests:$pytestCount},typescript:"PASS",vitest:{status:"PASS",tests:$vitestCount},viteBuild:"PASS",shellcheck:"PASS",postgresMigrations:"PASS",playwright:{status:"PASS",tests:$playwrightCount}},
    workflow:{customerRef:$customerRef,trainingJobsSucceeded:$trainingJobs,latestTrainingJob:$latestTrainingJob,demoOnlyModels:$demoModels,shadowOpportunities:$shadowOpportunities,simulationEvents:$simulationEvents,simulationSampleCount:$simulationSampleCount,latestSimulation:$latestSimulation,submittedEvents:$submittedEvents,approvedEvents:$approvedEvents,publishedEvents:$publishedEvents,activeNonRulesOnlyPolicies:0,screenshots:$screenshots},
    checks:{trainingJobPersisted:true,progressPolling:true,modelComparison:true,serverSideSimulation:true,simulationAuditPersisted:true,segregationOfDuties:true,selfApprovalRejected:true,activationBlockedAtG3:true,rulesOnlyOperationalPriority:true,mlShadowOnly:true,noCreditDecision:true},
    limitations:["SYNTHETIC_DATA_ONLY","DEMO_ONLY_MODELS_NOT_PROMOTABLE","NO_BOA_HISTORICAL_LABELS","G2_G3_NOT_PASSED","BLOCKED_IMAGE_CVES","NO_PRODUCTION_PERFORMANCE_CLAIM","AWS_OUT_OF_SCOPE"]
  }' >"$OUTPUT_FILE"
jq -e '.status=="PASS" and .releaseStatus=="BLOCKED" and .workflow.activeNonRulesOnlyPolicies==0 and .environment.frameworkVersion=="1.5.2"' "$OUTPUT_FILE" >/dev/null
printf 'ML_STUDIO_PASS runId=%s evidence=%s\n' "$RUN_ID" "$OUTPUT_FILE"
