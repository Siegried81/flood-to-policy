# flood-to-policy on Kubernetes

A learning port of `docker-compose.yml` to Kubernetes. Same three pieces: the
Streamlit app (8501), the FastAPI API (8010), and an Ollama sidecar (11434).

**Is k8s needed here?** No. One app this size belongs on Docker Compose or a PaaS
(Render, Railway). This port exists to practise the Kubernetes objects:
Deployment, Service, PersistentVolumeClaim, Secret, readiness probes.

## What maps to what

| Compose | Kubernetes |
|---|---|
| `app` service (Streamlit 8501) | Deployment + Service `flood-app` |
| `api` service (uvicorn 8010) | Deployment + Service `flood-api` |
| `ollama` service (11434) | Deployment + Service `flood-ollama` |
| `.env` file | Secret `flood-secrets` |
| `./data` bind mount | PVC `flood-data` |
| named volume `ollama_models` | PVC `flood-ollama-models` |
| compose `healthcheck` | `readinessProbe` |

Service names replace Compose DNS: the app reaches Ollama at
`http://flood-ollama:11434`, not `http://ollama:11434`.

## Run it locally with kind

```bash
# 1. a throwaway local cluster (Kubernetes in Docker)
kind create cluster --name flood

# 2. build the image and load it into the cluster (no registry needed)
docker build -t siegried/flood-to-policy:latest ..
kind load docker-image siegried/flood-to-policy:latest --name flood

# 3. secrets, then the app
kubectl create secret generic flood-secrets --from-env-file=../.env
kubectl apply -f flood-to-policy.yaml

# 4. watch it come up
kubectl get pods
kubectl logs deploy/flood-app
kubectl describe pod -l app=flood-app   # first stop if a pod won't start

# 5. reach the UI (no Ingress yet): forward the port to your machine
kubectl port-forward svc/flood-app 8501:8501
# open http://localhost:8501

# tear down
kind delete cluster --name flood
```

## Check the manifests without a cluster

```bash
kubectl apply --dry-run=client -f flood-to-policy.yaml
```

## Next step: an Ingress

`port-forward` is for one person debugging. For a real URL, add an Ingress that
routes `/` to `flood-app` and `/api` to `flood-api`, and terminates HTTPS. That
needs an ingress controller (e.g. ingress-nginx) in the cluster.
