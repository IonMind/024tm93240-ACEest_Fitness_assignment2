# Minikube deployment

The base manifests use the local image `aceest:local-test`. Build and load it before deploying:

```powershell
docker build -t aceest:local-test .
& "$env:LOCALAPPDATA\Programs\minikube\minikube.exe" image load aceest:local-test
kubectl create namespace aceest
```

Create a Kubernetes Secret named `aceest-secrets` in the `aceest` namespace from a private environment file outside the repository. It must contain `ACEEST_SECRET_KEY`, `ACEEST_ADMIN_USERNAME`, and `ACEEST_ADMIN_PASSWORD`, one `KEY=value` pair per line. Use a strong random secret key and password; do not commit the file or place credentials in screenshots.

```powershell
kubectl -n aceest create secret generic aceest-secrets --from-env-file=<private-file>
kubectl -n aceest apply -k k8s/base
kubectl -n aceest rollout status deployment/aceest
kubectl -n aceest port-forward service/aceest 8081:80
```

While port forwarding is active, open `http://127.0.0.1:8081`. The first database initialization creates the configured administrator. Changing the environment variables later does not change existing user credentials.

The PVC stores SQLite data across pod replacements. This base is for a single-node demonstration: SQLite has limited concurrent-write capacity, and storage and schema compatibility must be considered before running multiple versions. Protect and back up the database separately. Registry deployments must replace the local image reference with a published version.