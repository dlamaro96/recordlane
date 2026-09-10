#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
demo_compose="$project_root/deploy/compose/compose.demo.yaml"
production_compose="$project_root/deploy/compose/compose.production.yaml"
production_override="$project_root/tests/compose/compose.production-test.yaml"
production_env="$project_root/tests/compose/production-test.env"
production_project="recordlane-production-acceptance"
production_network="recordlane-production-acceptance"
kind_cluster="recordlane-acceptance"
port_forward_pid=""

cleanup() {
  if [ -n "$port_forward_pid" ]; then kill "$port_forward_pid" >/dev/null 2>&1 || true; fi
  docker compose -p "$production_project" --env-file "$production_env" -f "$production_compose" -f "$production_override" down --remove-orphans >/dev/null 2>&1 || true
  docker network disconnect "$production_network" recordlane-demo-postgres-1 >/dev/null 2>&1 || true
  docker network disconnect "$production_network" recordlane-demo-keycloak-1 >/dev/null 2>&1 || true
  docker network rm "$production_network" >/dev/null 2>&1 || true
  docker compose -p recordlane-demo -f "$demo_compose" exec -T postgres dropdb --if-exists --force -U recordlane_migrator recordlane_production_acceptance >/dev/null 2>&1 || true
  kind delete cluster --name "$kind_cluster" >/dev/null 2>&1 || true
}

on_exit() {
  status="$?"
  trap - EXIT
  if [ "$status" -ne 0 ] && kind get clusters 2>/dev/null | grep -Fxq "$kind_cluster"; then
    printf '\nKubernetes acceptance diagnostics:\n' >&2
    kubectl -n recordlane get all -o wide >&2 || true
    kubectl -n recordlane get events --sort-by=.metadata.creationTimestamp >&2 || true
    kubectl -n recordlane logs pod/postgres --all-containers --prefix >&2 || true
    kubectl -n recordlane logs job/recordlane-migrate-1 --all-containers --prefix >&2 || true
    kubectl -n recordlane describe job recordlane-migrate-1 >&2 || true
  fi
  cleanup
  exit "$status"
}
trap on_exit EXIT

# Remove only resources owned by a prior interrupted acceptance invocation so
# reruns remain deterministic without touching unrelated Docker or kind state.
cleanup
docker compose -p recordlane-demo -f "$demo_compose" up -d
docker network create "$production_network" >/dev/null
docker network connect --alias postgres "$production_network" recordlane-demo-postgres-1
docker network connect --alias keycloak "$production_network" recordlane-demo-keycloak-1
docker compose -p recordlane-demo -f "$demo_compose" exec -T postgres dropdb --if-exists -U recordlane_migrator recordlane_production_acceptance
docker compose -p recordlane-demo -f "$demo_compose" exec -T postgres createdb -U recordlane_migrator recordlane_production_acceptance
docker compose -p "$production_project" --env-file "$production_env" -f "$production_compose" -f "$production_override" config --quiet
docker compose -p "$production_project" --env-file "$production_env" -f "$production_compose" -f "$production_override" up -d

for _ in $(seq 1 90); do
  if curl --fail --silent http://127.0.0.1:18088/health/ready >/dev/null 2>&1; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:18088/health/ready >/dev/null
status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:18088/api/v1/overview)"
[ "$status" = "401" ]
[ "$(docker compose -p recordlane-demo -f "$demo_compose" exec -T postgres psql -At -U recordlane_migrator -d recordlane_production_acceptance -c 'select count(*) from schema_migrations;')" = "10" ]
for container in api worker web; do
  container_id="$(docker compose -p "$production_project" --env-file "$production_env" -f "$production_compose" -f "$production_override" ps -q "$container")"
  [ "$(docker inspect "$container_id" --format '{{.HostConfig.ReadonlyRootfs}}')" = "true" ]
  [ "$(docker inspect "$container_id" --format '{{json .HostConfig.CapDrop}}')" = '["ALL"]' ]
  [ "$(docker inspect "$container_id" --format '{{json .HostConfig.SecurityOpt}}')" = '["no-new-privileges:true"]' ]
done

docker buildx build --platform linux/arm64 --provenance=false --load -t recordlane-api:0.1.0-alpha.1 "$project_root/backend"
docker buildx build --platform linux/arm64 --provenance=false --load -t recordlane-web:0.1.0-alpha.1 "$project_root/apps/web"
docker buildx build --platform linux/arm64 --provenance=false --load \
  -f "$project_root/tests/kubernetes/Postgres.Dockerfile" \
  -t recordlane-postgres:17.6 "$project_root/tests/kubernetes"
kind delete cluster --name "$kind_cluster" >/dev/null 2>&1 || true
kind create cluster --name "$kind_cluster" --wait 90s
kind load docker-image --name "$kind_cluster" recordlane-api:0.1.0-alpha.1 recordlane-web:0.1.0-alpha.1 recordlane-postgres:17.6
kubectl create namespace recordlane
kubectl -n recordlane apply -f "$project_root/tests/kubernetes/postgres.yaml"
kubectl -n recordlane wait --for=condition=Ready pod/postgres --timeout=120s
kubectl -n recordlane create secret generic recordlane-database --from-literal=database-url='postgresql+psycopg://recordlane_migrator:demo-only-migrator@postgres:5432/recordlane'
kubectl -n recordlane create secret generic recordlane-migration-database --from-literal=database-url='postgresql+psycopg://recordlane_migrator:demo-only-migrator@postgres:5432/recordlane'
kubectl -n recordlane create secret generic recordlane-session --from-literal=session-secret='synthetic-kind-session-secret-acceptance'
kubectl -n recordlane create secret generic recordlane-master-key --from-file=master-key="$project_root/examples/demo/master-key.txt"
kubectl -n recordlane create secret generic recordlane-scim --from-literal=scim-token='synthetic-kind-scim-token'
kubectl -n recordlane create secret generic recordlane-metrics --from-literal=metrics-token='synthetic-kind-metrics-token'
helm lint "$project_root/deploy/helm/recordlane" -f "$project_root/tests/kubernetes/kind-values.yaml"
helm install recordlane "$project_root/deploy/helm/recordlane" -n recordlane -f "$project_root/tests/kubernetes/kind-values.yaml" --wait --timeout 180s
kubectl -n recordlane wait --for=condition=Available deployment/recordlane deployment/recordlane-worker --timeout=180s
kubectl -n recordlane get pods -l app.kubernetes.io/name=recordlane -o json | jq -e '
  [.items[].spec.containers[] |
    (.securityContext.allowPrivilegeEscalation == false and
     .securityContext.readOnlyRootFilesystem == true and
     .securityContext.capabilities.drop == ["ALL"])] | all
' >/dev/null
kubectl -n recordlane port-forward service/api 18089:80 >/tmp/recordlane-kind-port-forward.log 2>&1 &
port_forward_pid="$!"
for _ in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:18089/ >/dev/null 2>&1; then break; fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:18089/ >/dev/null
status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:18089/api/v1/overview)"
[ "$status" = "401" ]
printf 'production Compose and disposable kind/Helm acceptance passed\n'
