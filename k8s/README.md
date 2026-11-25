# flood-to-policy on Kubernetes

A learning port of `docker-compose.yml`: the Streamlit app (8501), the FastAPI API (8001)
and an Ollama Deployment (11434). One app this size belongs on Compose or a PaaS; this
exists to practise Deployment, Service, PersistentVolumeClaim, Secret and readiness probes.

| Compose | Kubernetes |
|---|---|
| `app` / `api` / `ollama` services | Deployment + Service `flood-app` / `flood-api` / `flood-ollama` |
| `.env` | Secret `flood-secrets` |
| `./data` bind mount | PVC `flood-data` (starts empty) |
| volume `ollama_models` | PVC `flood-ollama-models` (starts empty) |
| `healthcheck` | `readinessProbe` |

The `flood-api` pod reads `FLOOD_APPROVE_TOKEN` from `flood-secrets` and does not start without
it (the API refuses approvals without a token under Kubernetes); see `secret.example.yaml`. The
secret is otherwise optional. The Ollama image is pinned to `0.40.17`, the Ollama version installed on the dev machine.

Service names replace Compose DNS (`http://flood-ollama:11434`). `flood-data` is
ReadWriteOnce and mounted by two Deployments, which works only on a single node such as
kind; on several nodes use ReadWriteMany or one PVC each.

## Run it with kind

```bash
kind create cluster --name flood
docker build --target app -t siegried/flood-to-policy:latest ..    # `app` = code only
kind load docker-image siegried/flood-to-policy:latest --name flood
kubectl create secret generic flood-secrets --from-env-file=../.env   # must hold FLOOD_APPROVE_TOKEN
kubectl apply -f flood-to-policy.yaml
# the data PVC is empty: copy ../data in (one copy serves both pods), or mount the host
# folder into the kind node and use a hostPath volume instead of the PVC
kubectl cp ../data "$(kubectl get pod -l app=flood-app -o name | cut -d/ -f2):/app/data"
kubectl exec deploy/flood-ollama -- ollama pull llama3.2:3b          # the model, once
kubectl port-forward svc/flood-app 8501:8501                          # http://localhost:8501
kind delete cluster --name flood                                      # tear down
```

Check the manifests without a cluster: `kubectl apply --dry-run=client -f flood-to-policy.yaml`.
For a real URL add an Ingress routing `/` to `flood-app` and `/api` to `flood-api`.
