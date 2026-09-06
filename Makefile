# Docker Desktop k8s. Images build straight into the local daemon, which is why
# values-local.yaml sets pullPolicy: Never.
IMAGES = notes-api:dev notes-web:dev keycloak-notes:dev

.PHONY: compose test verify images deploy undeploy

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

deploy: images
	helm upgrade --install notes ./deploy/chart \
		-f deploy/chart/values-local.yaml \
		--namespace notes --create-namespace --wait

undeploy:
	helm uninstall notes --namespace notes
