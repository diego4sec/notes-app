# Docker Desktop runs Kubernetes on containerd, which cannot see images in the
# Docker daemon's store. So images go through a throwaway local registry.
REGISTRY = localhost:5001
# Tag used by deploy-ghcr. Pin a sha-<short> for anything you care about.
TAG ?= main
IMAGES = notes-api notes-web keycloak-notes

KC_ADMIN_PASSWORD ?= devadmin
# Keycloak's default Verify Profile policy requires both names. A user missing
# them is stopped at a profile form on first login, which also blocks any
# scripted sign-in.
FIRST_NAME ?= $(USER_NAME)
LAST_NAME ?= User
KCADM = /opt/keycloak/bin/kcadm.sh
KCCFG = --config /tmp/kcadm.json

# Gitignored, so a password never reaches a commit. Regenerate by deleting it.
SECRETS = deploy/chart/secrets.local.yaml

.PHONY: compose test verify images registry ingress secrets deploy deploy-ghcr undeploy user compose-user

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

# HTTP on 90, not 80: another app's LoadBalancer Service holds 80 on this
# cluster, and two LoadBalancers cannot share a host port.
ingress:
	helm upgrade --install ingress-nginx ingress-nginx \
		--repo https://kubernetes.github.io/ingress-nginx \
		--namespace ingress-nginx --create-namespace \
		--set controller.service.ports.http=90 --wait

registry: images
	docker start notes-registry 2>/dev/null || \
		docker run -d --restart=always -p 5001:5000 --name notes-registry registry:2
	for i in $(IMAGES); do \
		docker tag $$i:dev $(REGISTRY)/$$i:dev && docker push -q $(REGISTRY)/$$i:dev; \
	done

# The chart requires both passwords and refuses to render without them. This
# writes random ones once; re-running keeps what is already there, because
# Postgres only applies its password at initdb.
secrets:
	@if [ -f $(SECRETS) ]; then \
		echo "$(SECRETS) already exists, keeping it"; \
	elif kubectl -n notes get secret notes-secrets >/dev/null 2>&1; then \
		printf 'secret:\n  dbPassword: "%s"\n  keycloakAdminPassword: "%s"\n' \
			"$$(kubectl -n notes get secret notes-secrets -o jsonpath='{.data.db-password}' | base64 -d)" \
			"$$(kubectl -n notes get secret notes-secrets -o jsonpath='{.data.keycloak-admin-password}' | base64 -d)" > $(SECRETS); \
		echo "seeded $(SECRETS) from the deployed secret"; \
	else \
		printf 'secret:\n  dbPassword: "%s"\n  keycloakAdminPassword: "%s"\n' \
			"$$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)" \
			"$$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)" > $(SECRETS); \
		echo "wrote $(SECRETS) with new random passwords (gitignored)"; \
	fi

deploy: registry secrets
	helm upgrade --install notes ./deploy/chart \
		-f deploy/chart/values-local.yaml -f $(SECRETS) \
		--namespace notes --create-namespace --wait --timeout 8m

# Deploy the images CI published, rather than local builds. Add
# --set imagePullSecrets[0].name=ghcr if the GHCR packages are private.
deploy-ghcr: secrets
	helm upgrade --install notes ./deploy/chart \
		-f deploy/chart/values-local.yaml -f $(SECRETS) \
		--set api.image=ghcr.io/diego4sec/notes-api:$(TAG) \
		--set web.image=ghcr.io/diego4sec/notes-web:$(TAG) \
		--set keycloak.image=ghcr.io/diego4sec/keycloak-notes:$(TAG) \
		--namespace notes --create-namespace --wait --timeout 8m

undeploy:
	helm uninstall notes --namespace notes

# App users live in the `notes` realm of ONE Keycloak. The compose stack and the
# cluster have separate databases, so a user created in one cannot log in to the
# other. Password is prompted, not passed as an argument, so it stays out of
# your shell history. USER_NAME rather than USER, because USER is already an
# environment variable.
user:
	@test -n "$(USER_NAME)" || { echo "usage: make user USER_NAME=alice"; exit 1; }
	@printf 'password for %s: ' "$(USER_NAME)"; read -rs P; echo; \
	kubectl -n notes exec deploy/notes-keycloak -- $(KCADM) config credentials $(KCCFG) \
		--server http://localhost:8080/auth --realm master \
		--user admin --password '$(KC_ADMIN_PASSWORD)' && \
	kubectl -n notes exec deploy/notes-keycloak -- $(KCADM) create users $(KCCFG) -r notes \
		-s username='$(USER_NAME)' -s enabled=true -s emailVerified=true \
		-s email='$(USER_NAME)@example.com' \
		-s firstName='$(FIRST_NAME)' -s lastName='$(LAST_NAME)' && \
	kubectl -n notes exec deploy/notes-keycloak -- $(KCADM) set-password $(KCCFG) -r notes \
		--username '$(USER_NAME)' --new-password "$$P" && \
	echo "created $(USER_NAME) in the cluster notes realm"

compose-user:
	@test -n "$(USER_NAME)" || { echo "usage: make compose-user USER_NAME=alice"; exit 1; }
	@printf 'password for %s: ' "$(USER_NAME)"; read -rs P; echo; \
	docker compose exec -T keycloak $(KCADM) config credentials $(KCCFG) \
		--server http://localhost:8080/auth --realm master \
		--user admin --password admin && \
	docker compose exec -T keycloak $(KCADM) create users $(KCCFG) -r notes \
		-s username='$(USER_NAME)' -s enabled=true -s emailVerified=true \
		-s email='$(USER_NAME)@example.com' \
		-s firstName='$(FIRST_NAME)' -s lastName='$(LAST_NAME)' && \
	docker compose exec -T keycloak $(KCADM) set-password $(KCCFG) -r notes \
		--username '$(USER_NAME)' --new-password "$$P" && \
	echo "created $(USER_NAME) in the compose notes realm"
