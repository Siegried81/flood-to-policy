# flood-to-policy on Kubernetes

A learning port of `docker-compose.yml` to Kubernetes. Same three pieces: the
Streamlit app (8501), the FastAPI API (8010), and an Ollama Deployment (11434).

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

The `./data` row hides a gap: the bind mount showed the host folder, but a fresh
PVC is empty. Nothing is in it until step 3 below puts it there. `flood-data` is
also ReadWriteOnce and mounted by two Deployments, which only works because kind
is a single node. On a multi-node cluster you'd need ReadWriteMany or one PVC per
Deployment.

## Run it locally with kind

```bash
# 1. a throwaway local cluster (Kubernetes in Docker)
kind create cluster --name flood

# 2. build the image and load it into the cluster (no registry needed).
#    --target app is the code-only stage (about 1.6 GB); without it Docker
#    builds the last stage, `portable`, with the whole data/ tree baked in.
docker build --target app -t siegried/flood-to-policy:latest ..
kind load docker-image siegried/flood-to-policy:latest --name flood

# 3. secrets (optional, the pods start without them), then the app
kubectl create secret generic flood-secrets --from-env-file=../.env
kubectl apply -f flood-to-policy.yaml

# 4. data: the PVC starts empty. Copy ../data into the app pod (slow: 83 GiB,
#    70 of it HERA discharge files).
#    The api pod shares the same PVC, so one copy is enough.
kubectl cp ../data "$(kubectl get pod -l app=flood-app -o name | cut -d/ -f2):/app/data"
#    Or skip the copy: mount the host folder into the kind node at cluster
#    creation, then point a hostPath volume at /data instead of the PVC
#    (edit the `volumes:` of flood-app and flood-api in flood-to-policy.yaml).
#    kind config, saved as kind.yaml and used with `kind create cluster --config kind.yaml`:
#      kind: Cluster
#      apiVersion: kind.x-k8s.io/v1alpha4
#      nodes:
#        - role: control-plane
#          extraMounts:
#            - hostPath: ../data
#              containerPath: /data

# 5. the model: the Ollama PVC starts empty too, so pull once while online
kubectl exec deploy/flood-ollama -- ollama pull llama3.2:3b

# 6. watch it come up
kubectl get pods
kubectl logs deploy/flood-app
kubectl describe pod -l app=flood-app   # first stop if a pod won't start

# 7. reach the UI (no Ingress yet): forward the port to your machine
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
