# Docker Desktop runs Kubernetes on containerd, which cannot see images in the
# Docker daemon's store. So images go through a throwaway local registry.
REGISTRY = localhost:5001
IMAGES = notes-api notes-web keycloak-notes

.PHONY: compose test verify images registry deploy undeploy

compose:            ## phase 1: db + keycloak + api, SPA runs via `cd web && npm run dev`
	docker compose up -d --build

test:
	cd api && uv run --extra dev pytest

# Real browser flow against a running stack: PKCE, issuer, audience, role gate.
verify:
	python3 scripts/verify-auth-flow.py

images:
	docker build -t notes-api:dev ./api
	docker build -t notes-web:dev ./web
	docker build -t keycloak-notes:dev ../keycloak-notes

registry: images
	docker start notes-registry 2>/dev/null || \
		docker run -d --restart=always -p 5001:5000 --name notes-registry registry:2
	for i in $(IMAGES); do \
		docker tag $$i:dev $(REGISTRY)/$$i:dev && docker push -q $(REGISTRY)/$$i:dev; \
	done

deploy: registry
	helm upgrade --install notes ./deploy/chart \
		-f deploy/chart/values-local.yaml \
		--namespace notes --create-namespace --wait --timeout 8m

undeploy:
	helm uninstall notes --namespace notes
