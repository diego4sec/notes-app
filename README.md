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

## Commands

| Command | What it does |
|---|---|
| `make compose` | Phase 1: db, Keycloak, API, and a `dev` user. SPA runs separately. |
| `make test` | pytest against Postgres. Needs only `docker compose up -d db`. |
| `make verify` | Real PKCE login plus API calls. Needs a whole stack up. |
| `make images` | Builds the three images into the local Docker daemon. |
| `make registry` | Pushes those images to a throwaway registry on `localhost:5001`. |
| `make ingress` | Installs ingress-nginx with HTTP on port 90. |
| `make deploy` | `registry` plus `helm upgrade --install` with `values-local.yaml`. |
| `make undeploy` | `helm uninstall`. Leaves the namespace and the PVC. |
| `make user USER_NAME=x` | Creates an app user in the cluster realm. Prompts for the password. |
| `make compose-user USER_NAME=x` | Same, in the compose realm. |

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

A fresh cluster has no users. See **Creating users** below.

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
    deploy/initdb/  creates the keycloak database next to the notes one
    docker-compose.yml
    Makefile        every command above

## Creating users

    make user USER_NAME=alice            # cluster (the app on :90)
    make compose-user USER_NAME=alice    # compose (the app on :5173)

The password is prompted, not passed as an argument, so it stays out of your
shell history.

**There are two separate Keycloaks, each with its own database.** A user
created in one cannot log in to the other, and the browser only says "Invalid
username or password", which is a confusing way to learn this.

| Stack | App URL | Admin console | Admin login |
|---|---|---|---|
| compose | http://localhost:5173 | http://localhost:8080/auth/admin/ | `admin` / `admin` |
| kubernetes | http://notes.localhost:90 | http://notes.localhost:90/auth/admin/ | `admin` / `devadmin` |

Doing it by hand in the admin console works too, with three things that are
easy to get wrong:

1. **Pick the `notes` realm, not `master`.** `master` administers Keycloak
   itself; app users do not belong there.
2. **Set first and last name.** Keycloak's default Verify Profile policy stops
   a user with either missing at a profile form on first login, and blocks
   scripted sign-in entirely.
3. **Set a password on the Credentials tab,** with Temporary off unless you
   want the reset prompt.

The realm grants `notes-user` by default, so a new user can use the API
straight away. Strip that role and the API returns 403 rather than 401, since
the caller is authenticated but not entitled.

When a login fails for no visible reason, see **Troubleshooting** below.

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

## Troubleshooting

### A login fails and the browser just says invalid credentials

Keycloak logs the real reason. This is the single most useful command here:

    kubectl -n notes logs deploy/notes-keycloak --tail=200 | grep LOGIN_ERROR
    docker compose logs keycloak | grep LOGIN_ERROR          # compose

| In the log | Actually wrong |
|---|---|
| `error="user_not_found"` | Wrong Keycloak instance, or wrong realm. By far the most common. |
| `error="invalid_user_credentials"` | The password. |
| `error="cookie_not_found"` | The browser dropped Keycloak's `Secure` cookies, because the origin is not trustworthy. Use `localhost` / `*.localhost` over plain HTTP, or run TLS. |
| redirect to `required-action?execution=VERIFY_PROFILE` | User has no first or last name. |
| `error="invalid_redirect_uri"` | The URL's port is not in the client's redirect URIs. Keycloak matches them including the port. |

### Am I locked out?

Almost certainly not, and it is worth checking before assuming so:

    kubectl -n notes exec deploy/notes-keycloak -- /opt/keycloak/bin/kcadm.sh \
      get attack-detection/brute-force/users/<user-id> --config /tmp/kcadm.json -r notes

The realm has `bruteForceProtected: true`, but `failureFactor` is 30 and
`permanentLockout` is false, so a lockout takes 30 failures and then clears
itself (60s increments, capped at 900s). Failures against a username that does
not exist lock nothing at all, because the counter attaches to a user id and
there is none.

To clear every lockout in the realm without touching users:

    kubectl -n notes exec deploy/notes-keycloak -- /opt/keycloak/bin/kcadm.sh \
      delete attack-detection/brute-force/users --config /tmp/kcadm.json -r notes

### Pods stuck on ErrImageNeverPull

Docker Desktop runs Kubernetes on containerd, which cannot see the Docker
daemon's image store. Run `make deploy`, which pushes through the local
registry, rather than pointing the chart at a locally built tag.

### Nothing answers on the app URL

    kubectl -n ingress-nginx get svc ingress-nginx-controller

`<pending>` in the EXTERNAL-IP column means the port it asked for is already
taken on the host, usually by another LoadBalancer Service. Two of them cannot
share a host port, and the loser waits forever with no error.

### Every API call returns 401

The token issuer does not match what the API validates. Compare them:

    curl -s http://notes.localhost:90/auth/realms/notes/.well-known/openid-configuration \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["issuer"])'
    kubectl -n notes exec deploy/notes-api -- printenv OIDC_ISSUER

They must be byte-identical, port included. `KC_HOSTNAME` must carry the
`/auth` path, and `port` in the values file must match the port in the URL bar.

### Every API call returns 403

Authenticated but not entitled: the user is missing the `notes-user` realm
role. The realm grants it by default, so this means it was removed, or the user
came from somewhere that does not grant it.

## Not built

CI pipelines, note sharing, attachments, note history, rate limiting,
observability. Each is a deliberate omission, not an oversight.

## Known gaps

The SPA's own JavaScript has never been exercised in a browser. It builds, the
image serves it, and the OIDC flow it depends on is verified end to end by
`make verify`, but nobody has confirmed the React app behaves once loaded.

Realm changes are import-only, so editing `notes-realm.json` does not update a
running realm. Locally, drop the Keycloak database. In cloud, `importRealm` is
off and the realm is managed deliberately.
