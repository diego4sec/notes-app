# notes-app

A note manager. Authentication comes from the `keycloak-notes` repo as a
pinned container image.

## Shape

    web (React SPA)  ->  api (FastAPI)  ->  Postgres
             \                /
              Keycloak (issuer)

One host serves all three behind one ingress:

    /       ->  web       static bundle
    /api    ->  api       FastAPI, no path rewriting
    /auth   ->  keycloak  KC_HTTP_RELATIVE_PATH=/auth

That single-host layout is load-bearing, not cosmetic. It makes the token
issuer identical for the browser and for the API, which is what removes the
most common failure in this setup, and it removes CORS entirely.

## Phase 1: local, no Kubernetes

Clone both repos as siblings:

    parent/
      keycloak-notes/
      notes-app/

Then:

    make compose                      # db + keycloak + api + dev user
    cd web && npm install && npm run dev

- app: http://localhost:5173
- login: `dev` / `dev`
- api docs: http://localhost:8000/api/docs
- keycloak admin: http://localhost:8080/auth/admin/ (`admin` / `admin`)

The SPA runs on the host rather than in compose so Vite can hot-reload and so
nothing gets baked into a web image.

## Phase 2: Kubernetes on Docker Desktop

Enable Kubernetes in Docker Desktop, then once:

    make ingress

That installs ingress-nginx with its HTTP port on **90**, not 80. Two
LoadBalancer Services cannot share a host port, and port 80 on this cluster
belongs to another app. A LoadBalancer asking for a taken port never gets an
address: it sits at `<pending>` and nothing answers, with no error to explain
it. If port 80 is free where you are, use `--set controller.service.ports.http=80`
and set `port: ""` in `values-local.yaml`.

Then:

    make deploy

`make deploy` builds the three images, pushes them to a throwaway registry on
`localhost:5001`, and installs the chart. The registry is not optional:
Docker Desktop runs Kubernetes on containerd, which cannot see images in the
Docker daemon's own store, so a locally built image with `pullPolicy: Never`
fails with `ErrImageNeverPull`.

Open **http://notes.localhost:90**. It resolves to 127.0.0.1 with no
`/etc/hosts` edit, and browsers treat `*.localhost` as a trustworthy origin.

The port has to appear in `values-local.yaml` as `port: 90`, not just in the
URL: it flows into `KC_HOSTNAME` and therefore into the token issuer, and it is
matched exactly in the client's redirect URIs.

**If nothing answers,** check that the ingress Service actually got an
address:

    kubectl -n ingress-nginx get svc ingress-nginx-controller

`<pending>` means the port it asked for is already taken on the host. Either
move the controller to a free port and set `port` to match, or reach it through
a port-forward:

    kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8081:90
    helm upgrade --install notes ./deploy/chart -f deploy/chart/values-local.yaml \
      --set port=8081 --namespace notes

The realm lists `:90` and `:8081`. Any other port must be added to the
client's redirect URIs, because Keycloak matches them including the port.

A fresh cluster has no users. The compose seed does not apply here:

    kubectl -n notes exec -it deploy/notes-keycloak -- /opt/keycloak/bin/kcadm.sh \
      config credentials --server http://localhost:8080/auth --realm master \
      --user admin --password devadmin
    kubectl -n notes exec -it deploy/notes-keycloak -- /opt/keycloak/bin/kcadm.sh \
      create users -r notes -s username=dev -s enabled=true -s email=dev@example.com
    kubectl -n notes exec -it deploy/notes-keycloak -- /opt/keycloak/bin/kcadm.sh \
      set-password -r notes --username dev --new-password dev

The realm grants `notes-user` by default, so a user created this way can use
the API immediately. Without that role the API returns 403.

That last part is not cosmetic. Keycloak sets its auth cookies
`Secure; SameSite=None`, and a browser only accepts `Secure` cookies from a
trustworthy origin. Over plain HTTP, `*.localhost` qualifies and something like
`*.localtest.me` does not, so using the latter here produces a login that
silently loops with no error anywhere. The alternative is to run TLS locally.

There are no users in a fresh cluster. Create one in the admin console at
http://notes.localhost/auth/admin/ or with `kcadm.sh` (see `helm status`).

## Phase 3: cloud

    helm upgrade --install notes ./deploy/chart -f deploy/chart/values-cloud.yaml \
      --namespace notes --create-namespace

Same chart. `values-cloud.yaml` changes only what has to change:

| | local | cloud |
|---|---|---|
| Postgres | in-cluster StatefulSet | managed, `postgres.enabled=false` |
| TLS | off | cert-manager, `tls.clusterIssuer` |
| Secrets | literals in values | `secret.create=false`, from a real store |
| Realm import | on | **off** |
| Replicas | 1 | 2, with limits |

Before the first cloud deploy you need: a DNS record for `host`, cert-manager
with a `ClusterIssuer`, a managed Postgres with a `keycloak` database created,
and a `notes-secrets` Secret holding `db-password` and
`keycloak-admin-password`.

## Layout

    api/            FastAPI, SQLAlchemy, Alembic
      app/auth.py     the whole Keycloak integration, ~40 lines
      app/models.py   one table
      tests/          the one check
    web/            React, Vite, react-oidc-context
    deploy/chart/   one Helm chart, three values files
    scripts/        verify-auth-flow.py, the end-to-end auth check
    docker-compose.yml

## Data model

One table. Notes are owned by a Keycloak `sub` and that is the whole identity
model:

    note(id, owner_id, title, body, tags text[], created_at, updated_at, deleted_at)

- **No `app_user` table.** Identity lives in Keycloak; email and name come off
  the token. A local user directory only becomes necessary once notes are
  shared between people.
- **Tags are `text[]` with a GIN index,** not `tag` + `note_tag` tables. Tags
  are owner-scoped, so normalising them buys no shared vocabulary and costs two
  tables and a join.
- **Search is Postgres full-text search** over `title || ' ' || body`. The
  expression in `app/routers/notes.py` must stay textually identical to the one
  in the migration, or Postgres will not use the index.

## Security decisions worth keeping

- `notes-web` is a **public** client using PKCE. There is no client secret,
  because anything shipped to a browser is public.
- `notes-api` is **bearer-only**. Every request validates signature, `iss` and
  `aud`. A token minted for another audience is rejected.
- **Ownership comes from the `sub` claim, never from the request.** It is a
  `WHERE` clause on every query, not a filter applied afterwards.
- **A valid token is not permission.** Every request also requires the
  `notes-user` realm role, so a token minted for another app in the same realm
  gets a 403 rather than access. The realm grants that role by default, and
  `notes-admin` exists for a future admin view.
- Reads of someone else's note return **404, not 403**. A 403 confirms the note
  exists.
- Tokens live in `sessionStorage`, which any XSS on this origin can read. The
  upgrade path is a BFF holding them in httpOnly cookies, which is an extra
  service and was not worth it yet.
- The Keycloak image ships **no users**, so no known password lives in an image
  layer.
- Containers run as non-root; the API additionally runs with a read-only root
  filesystem and all capabilities dropped.
- Passwords come from a Secret ref. `secret.create=true` refuses to render with
  empty values, so a cloud deploy cannot quietly ship a blank password.

## Testing

Two layers, because they catch different things.

    make test        # needs Postgres: docker compose up -d db

Covers CRUD, owner isolation across three verbs, that search and tag filters
stay owner-scoped, the role gate, and payload validation. Needs a real
Postgres, because the schema uses `text[]` and Postgres full-text search.

    make verify      # needs the whole stack up

Drives the real authorization-code + PKCE flow with no browser, then calls the
API with the resulting token. This is the layer that catches what unit tests
structurally cannot see, and each of these actually bit during development:

| Symptom | Cause |
|---|---|
| API 401s every token | `KC_HOSTNAME` had no `/auth` path, so Keycloak served at `/auth` but advertised an issuer without it |
| login silently loops | Keycloak's auth cookies are `Secure`; the browser origin was not trustworthy, so they were dropped |
| `KeyError: sub` | hand-listing `defaultClientScopes` dropped Keycloak's `basic` scope, which is what carries `sub` |
| no roles in token | `fullScopeAllowed: false` with no `scopeMappings`, and a `defaultRole` block whose composites never imported |

It also works against the cluster:

    KC_BASE=http://notes.localhost:90/auth/realms/notes \
    API_BASE=http://notes.localhost:90 REDIRECT=http://notes.localhost:90/ \
    KC_USER=you KC_PASSWORD=... make verify

## Not built

CI pipelines, note sharing, attachments, note history, rate limiting,
observability. Each is a deliberate omission, not an oversight.
