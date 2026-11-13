# Helm chart

The chart deploys TRS-Filer on Kubernetes (and OpenShift): the app and a
MongoDB database. It is a thin chart over FOCA's library chart `foca-common`
(the version in `Chart.yaml`), which renders the resources from the values
described here and in `values.yaml` (see the [library chart's
documentation](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md)).
The chart in the repository downloads the library chart with `helm
dependency build` (see [Installation](#installation)).

> **Note:** Writes (registering, changing and deleting tools and tool
> classes) need an access token of an admin of your OpenID Connect provider;
> reads are public. Set the provider and the admin group in `config` (see
> [Configuration](#configuration)): rendering fails without them.

## Configuration

The image contains the app's complete base config
([`trs_filer/config.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/config.yaml)).
The chart renders a config overlay into the `<app>-config` ConfigMap (see
[Names and labels](#names-and-labels)), which FOCA merges into the base
config on startup (via `FOCA_CONFIG_OVERLAY`):

- `custom.service` is set to the public URL of the app, `https://<hostName>`
  on port 443, which the app puts into the `url` of tools and versions;
  `hostName` is **required** (rendering fails without it). Serve the app over
  HTTPS for it (see [Exposing the app](#exposing-the-app)).
- `db.host` is set to the release's MongoDB Service (`<app>-mongodb`),
  unless MongoDB is external (see [External MongoDB](#external-mongodb)).
- `config` overrides keys of the base config; it takes precedence over the
  generated values. Mappings are merged recursively, all other values
  (including lists) replace those of the base config (see
  [Configuration](https://trs-filer.readthedocs.io/en/latest/configuration/)).
  `server.host` and `server.port` have no effect, as they apply to the
  development server only (see [Server](#server)).

The identity provider is deployment configuration, without defaults (see
[Access control](https://trs-filer.readthedocs.io/en/latest/access-control/)
and [Deployment
configuration](https://trs-filer.readthedocs.io/en/latest/configuration/#deployment-configuration)).
Rendering fails, as the app would refuse to start, unless each deployment
sets:

- access control, enabled and enforced (as by default:
  `config.security.access_control.enabled` and `enforce`), so that only
  admins can write;
- the trusted token issuers (`config.security.auth.issuers`): URLs, or maps
  of the URL (`issuer`) and settings of the issuer (e.g., `audience`,
  `claim_groups`, `userinfo_claims`);
- the audience (`config.security.auth.audience`), unless
  `config.security.auth.verify_audience` is `false`, which accepts tokens for
  any audience, or each issuer is a map with an `audience` of its own;
- an admin group mapped to the role `admin`
  (`config.security.access_control.group_mapping`), unless
  `config.security.access_control.require_admin` is `false`; the chart
  counts only group mappings, so set it to `false` if only rules of
  `config.security.access_control.policies` grant the role;
- the claim with the groups of users
  (`config.security.access_control.claim_groups`, or `claim_groups` of an
  issuer), if groups are mapped.

The app checks the other settings on startup and refuses to start, with the
reason in its log (check with `kubectl logs` and `kubectl rollout status`
after installs and upgrades).

Keep the values of each deployment in its own values file outside this
repository (e.g., `values-prod.yaml` in the deployment's infrastructure
repository), for example:

```yaml
hostName: trs.example.org
mongodb:
  auth:
    existingSecret: trs-filer-mongodb-credentials
config:
  security:
    auth:
      # Trusted token issuers (`iss` claim)
      issuers: ["https://login.example.org/oidc/"]
      # Client IDs of the apps that register tools
      audience: ["trs-portal"]
      # Claims released via user info only, not in access tokens
      userinfo_claims: ["groups"]
    access_control:
      # Claim with the groups of users
      claim_groups: groups
      group_mapping:
        trs-admins: admin
  service_info:
    service:
      id: org.example.trs
      name: Example TRS
      organization:
        name: Example Organization
        url: https://example.org
      contactUrl: mailto:trs-admins@example.org
      environment: prod
```

Without `service_info`, deployments serve the **placeholder service info**
of the base config (`id: org.example.trs-filer`, organization `Example
Organization`), and FOCA warns of it on startup. Pods are restarted when the
ConfigMap changes. Don't edit the ConfigMap with `kubectl edit`: Helm
overwrites it on the next upgrade. As `config` is stored in a ConfigMap, it
must not contain secrets; pass them as environment variables from Secrets
(`trsFiler.extraEnv`, `trsFiler.extraEnvFrom`, see [Server](#server)).

## Image

The app image is `trsFiler.image` (default `docker.io/elixircloud/trs-filer`)
with tag `trsFiler.tag`, which defaults to the chart's `appVersion`. Charts
attached to [GitHub
releases](https://github.com/elixir-cloud-aai/trs-filer/releases) have the
release version as `version` and `appVersion`, so they deploy the image of
their release. In the repository, both are placeholders, and `appVersion`
is `dev`: the chart deploys the latest image of branch `dev`, which changes
with every commit. Deployments from the repository should set the tag of a
release (e.g., `{{ version }}`) or of a commit on `dev` (`sha-<commit>`, the
full commit SHA) in the values file:

```yaml
trsFiler:
  tag: sha-0123456789abcdef0123456789abcdef01234567
```

`trsFiler.image` may also include a tag or digest (e.g.,
`docker.io/elixircloud/trs-filer:{{ version }}`, as in earlier charts); then
`trsFiler.tag` must be empty. See [Versioning and
releases](https://trs-filer.readthedocs.io/en/latest/development/#versioning-and-releases)
for the image tags.

The image is pulled on every start of a pod (`trsFiler.imagePullPolicy:
Always`), so that moving tags such as `dev` deploy the latest image; set
`IfNotPresent` for fixed tags or digests, or `Never` for images loaded into
the nodes (e.g., with `kind load`).

## Installation

MongoDB requires authentication: create a Secret with its credentials in the
namespace first, and set its name in `mongodb.auth.existingSecret` (see
[Authentication](#authentication)); otherwise, rendering fails. E.g., with
random passwords:

```bash
kubectl create namespace <namespace>
kubectl create secret generic trs-filer-mongodb-credentials -n <namespace> \
    --from-literal=root-username=root \
    --from-literal=root-password="$(openssl rand -hex 24)" \
    --from-literal=username=trs-filer \
    --from-literal=password="$(openssl rand -hex 24)"
```

Install the chart attached to a release (`trs-filer-{{ chart_version }}.tgz`
of the latest release, `{{ version }}`), which sets the release's image. It
is signed and has a build attestation: download and verify it before you
install it (see [Verifying images and
charts](https://trs-filer.readthedocs.io/en/latest/operations/#verifying-images-and-charts)
for the signature check with cosign and the details).

```bash
gh release download v{{ version }} --repo elixir-cloud-aai/trs-filer \
    --pattern 'trs-filer-{{ chart_version }}.tgz*'
gh attestation verify trs-filer-{{ chart_version }}.tgz \
    --repo elixir-cloud-aai/trs-filer \
    --signer-workflow elixir-cloud-aai/trs-filer/.github/workflows/release.yml \
    --source-ref refs/tags/v{{ version }}
```

If the verification succeeds, install the chart:

```bash
helm install trs-filer trs-filer-{{ chart_version }}.tgz -n <namespace> \
    -f values-prod.yaml
```

The package contains the library chart. To install the chart from the
`deployment` folder of the repository instead (e.g., to test changes of the
chart), download the library chart (into `charts/`, the version locked in
`Chart.lock`), and set `trsFiler.tag` (see [Image](#image)), as the chart
deploys the moving `dev` image otherwise:

```bash
helm dependency build deployment
helm install trs-filer deployment -n <namespace> -f values-prod.yaml
```

`<namespace>` is the namespace to deploy to; `trs-filer` is the name of the
release, which is referenced when upgrading or uninstalling. Helm prints the
app's URL and a test request after installing (`helm get notes trs-filer -n
<namespace>` shows them again; `helm show values` prints the defaults).

## Names and labels

Resource names are derived from the release name, so that several releases
can be installed in one namespace:

- **App** (Deployment, Service, Ingress, HTTPRoute or Route, NetworkPolicy,
  PodDisruptionBudget; ConfigMap `<app>-config`): `<app>` is
  `<release>-trs-filer`, or the release name if it contains `trs-filer`
  (e.g., `trs-filer` for the release `trs-filer`, `prod-trs-filer` for the
  release `prod`);
- **MongoDB** (Deployment, Service, PersistentVolumeClaim, NetworkPolicy;
  ConfigMap `<app>-mongodb-init-script`): `<app>-mongodb`; the app connects
  to this Service.

`nameOverride` replaces `trs-filer` in the names and the
`app.kubernetes.io/name` label, `fullnameOverride` replaces `<app>`. Set them
when installing only: changing them later changes the pod selectors of the
Deployments, which can't be changed, so the upgrade fails, and MongoDB's
claim. Names are truncated to 63 characters. The examples in this document
use the release `trs-filer`.

All resources have the [standard
labels](https://helm.sh/docs/chart_best_practices/labels/)
(`app.kubernetes.io/name`, `instance`, `version` and `managed-by`, and
`helm.sh/chart`); pods are selected by name, instance and
`app.kubernetes.io/component` (`app` or `mongodb`), e.g.:

```bash
kubectl get pods -n <namespace> -l app.kubernetes.io/instance=trs-filer
```

## Exposing the app

The chart exposes the app for `hostName` in one of three ways (see
[Exposing the
app](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#exposing-the-app)
in the library chart's documentation for TLS, body size and rate limits,
NetworkPolicy peers and keep-alive settings of ingress-nginx, Traefik, the
Gateway API, OpenShift and cloud load balancers):

- an Ingress (`trsFiler.ingress`, enabled by default), for any ingress
  controller; `className` sets its class, `annotations` its annotations
  (e.g., for the ingress controller; they take precedence over those set by
  the chart for `https`, `null` removes one), and `https.enabled` requests a
  certificate from cert-manager (via the ClusterIssuer `https.issuer`);
- a Gateway API HTTPRoute (`trsFiler.httpRoute`), attached to an existing
  Gateway (`parentRefs`), optionally with a second HTTPRoute that redirects
  HTTP to HTTPS (`httpsRedirect`); set `trsFiler.ingress.enabled: false` to
  use it, e.g.:

    ```yaml
    trsFiler:
      ingress:
        enabled: false
      httpRoute:
        enabled: true
        parentRefs:
        - name: gateway
          namespace: gateway-system
          sectionName: https
        httpsRedirect:
          enabled: true
          parentRefs:
          - name: gateway
            namespace: gateway-system
            sectionName: http
    ```

- an OpenShift Route, with TLS termination at the router, which redirects
  HTTP to HTTPS, if neither is enabled, the cluster serves Routes
  (`route.openshift.io/v1`) and `trsFiler.route.enabled` is true (the
  default); otherwise the app is only reachable within the cluster, and Helm
  prints a warning after installing. On OpenShift (e.g., CSC's Rahti),
  disable the Ingress, which is enabled by default and has no TLS unless you
  configure it: the chart then creates the Route.

All of them route all paths (`/`) to the app, including FOCA's permissions
API (`/admin/access-control/`, for admins only; see [Permissions
API](https://trs-filer.readthedocs.io/en/latest/operations/#permissions-api)).
To keep that API off the internet, block `/admin/` in the proxy in front of
the cluster, or disable the chart's Ingress (and, on OpenShift, its Route:
`trsFiler.route.enabled: false`) and create one of your own that routes only
`/ga4gh/trs/v2/` to the app's Service (port `http`).

The app advertises `https://<hostName>` URLs (e.g., the `url` of tools), and
clients send bearer tokens with writes, so serve the app over HTTPS only: by
default, the Ingress has no TLS (`https.enabled: false`) and serves plain
HTTP, so TLS must be terminated in front of the cluster (e.g., by a load
balancer); Helm's notes after installing say so.

The app rejects request bodies over `config.server.max_content_length`
bytes (default: 1 MiB, see [Server](#server)) in every setup; the chart sets
no limit at the proxy. ingress-nginx limits request bodies to 1 MiB by
default, the app's default: if you raise the app's limit, raise that of
ingress-nginx too (`nginx.ingress.kubernetes.io/proxy-body-size` in
`trsFiler.ingress.annotations`). The app has no rate limits of its own, and
the chart sets none at the proxy: for production, limit the rate of
requests per client at the ingress controller or Gateway (see the library
chart's documentation, linked above).

Writes need an access token of an admin (see
[Configuration](#configuration)). To also allow the methods that change
data (`POST`, `PUT`, `DELETE`) only from trusted clients, use the means of
your ingress controller, Gateway or proxy. For example (an example only,
adapt it to your setup), with ingress-nginx, which allows them only from the
network `192.0.2.0/24`:

```yaml
trsFiler:
  ingress:
    className: nginx
    annotations:
      nginx.ingress.kubernetes.io/configuration-snippet: |
        limit_except GET HEAD OPTIONS {
          allow 192.0.2.0/24;
          deny all;
        }
```

`allow` checks the source address that the controller sees, which is the
client's only if it gets through: behind a load balancer, e.g., with
`externalTrafficPolicy: Local` or the PROXY protocol. If the controller
trusts forwarded headers (`use-forwarded-headers`), limit them to your
proxies (`proxy-real-ip-cidr`), or anyone can claim an allowed address in
`X-Forwarded-For`. Recent versions of ingress-nginx disable snippet
annotations by default (the controller must allow them,
`allow-snippet-annotations`, and annotations of their risk level,
`annotations-risk-level: Critical`), as they let anyone who can create
Ingresses change the controller's configuration; a controller that doesn't
allow them ignores the annotation (or rejects the Ingress), leaving writes
unrestricted at the controller. ingress-nginx is also retired (no releases
or security fixes after March 2026). The OpenShift router can't restrict
methods, only clients, for all methods (e.g.,
`haproxy.router.openshift.io/ip_allowlist: 192.0.2.0/24` in
`trsFiler.route.annotations`; `ip_whitelist` before OpenShift 4.14). In
every setup, check with a `POST` from an untrusted address that writes are
refused.

### Forwarded headers

The ingress controller, Gateway or router terminates TLS and forwards
requests to the app via HTTP, with `X-Forwarded-*` headers. Gunicorn trusts
these headers from the local host only (its default), so the links that the
app builds from the request (the `self_link` and `next_page` headers of tool
listings) get `http`; the `url` of tools and versions comes from `hostName`
(see [Configuration](#configuration)) and is not affected. To keep `https`
in these links, set the addresses that the ingress controller or router
connects from in Gunicorn's `FORWARDED_ALLOW_IPS`, via `trsFiler.extraEnv`:
addresses or networks in CIDR notation, comma-separated (e.g., the nodes'
subnet if the controller runs in the host network):

```yaml
trsFiler:
  extraEnv:
  - name: FORWARDED_ALLOW_IPS
    value: "192.0.2.0/24"
```

Every workload that can reach the app's pods from a trusted address can set
these headers, and so the scheme of these links (and their path, via
Gunicorn's `SCRIPT_NAME` header); the host of the links comes from the
`Host` header, which every client that reaches the pod sets. So never use
`*` (as earlier charts did by default) if clients can reach the app's pods
directly: a network trusts every address in it, and the pod network of the
cluster (e.g., `10.128.0.0/14` on OpenShift) contains every pod; restrict
who can reach the app's pods with its NetworkPolicy (see [Network
policies](#network-policies)). An invalid entry stops the app (Gunicorn
exits on startup). Check afterwards that a listing through the Ingress or
Route gives `https` links (e.g., `curl -sI
'https://trs.example.org/ga4gh/trs/v2/tools?limit=1'` and its `self_link`
header).

## Security context

All containers run as non-root users, without privilege escalation or
capabilities, with the runtime's default seccomp profile and a read-only
root file system, as the Pod Security Standard "restricted" requires; they
write to `emptyDir` volumes (`/tmp`) and MongoDB to its data volume. The app
image runs as user 1000; the MongoDB image uses user 999, which the chart
sets (`runAsUser`, `runAsGroup`), and `fsGroup` makes its data volume
writable (applied on a mismatch only, `fsGroupChangePolicy:
OnRootMismatch`). This needs storage that applies `fsGroup` (most
dynamically provisioned volumes do; e.g., `hostPath` and some CSI drivers
don't): otherwise, MongoDB can't write to a new volume and doesn't start. No
pod gets a service account token (`automountServiceAccountToken: false`), as
none calls the Kubernetes API.

The `/tmp` volumes are limited to 64 MiB each by `tmpSizeLimit` of
`trsFiler` and `mongodb` (a positive Kubernetes quantity, e.g., `64Mi`, or a
number of bytes; `null` removes the limit); the kubelet evicts pods that
exceed it.

On OpenShift (detected by the API `security.openshift.io/v1`), the chart
omits `runAsUser`, `runAsGroup` and `fsGroup`, as OpenShift assigns them
from the namespace's range. The contexts are set in the values
(`podSecurityContext` and `securityContext` of `trsFiler` and `mongodb`);
mappings are merged with the defaults, and `null` removes a default. Some
clusters set their own seccomp profile and reject pods that ask for one,
such as the chart's default (`seccompProfile: {type: RuntimeDefault}`); on
such clusters, remove it (`trsFiler.podSecurityContext.seccompProfile: null`
and `mongodb.podSecurityContext.seccompProfile: null`), and the pods run
with the profile that the cluster assigns.

## Network policies

The chart creates
[NetworkPolicies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
that restrict which pods may connect to its pods (ingress); connections from
the pods, e.g., of the app to the token issuers, are not restricted. They
only take effect if the cluster's network plugin enforces NetworkPolicies
(e.g., Calico or Cilium). NetworkPolicies add up: a pod that several
policies select accepts the connections that any of them allows (e.g., a
namespace-wide "allow" policy).

- **MongoDB** (`mongodb.networkPolicy.enabled`, default `true`): only the
  app's pods of the same release may connect. Disable it if you manage
  policies yourself, or if other workloads (e.g., backups) must connect.
- **App** (`trsFiler.networkPolicy.enabled`, default `false`): only the
  NetworkPolicy peers in `trsFiler.networkPolicy.ingressFrom` may connect.
  There are none by default, as they depend on the cluster: when enabling
  the policy, set them to the pods of the cluster's ingress controller,
  Gateway or OpenShift router (see [NetworkPolicy
  peers](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#networkpolicy-peers)
  in the library chart's documentation), and add other clients in the
  cluster that call the app's Service directly; otherwise, the app is
  unreachable through the Ingress (or Route). Rendering fails if the policy
  is enabled without peers (which would allow all sources), e.g.:

    ```yaml
    trsFiler:
      networkPolicy:
        enabled: true
        ingressFrom:
        # ingress-nginx: its pods in the namespace `ingress-nginx`
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
          podSelector:
            matchLabels:
              app.kubernetes.io/name: ingress-nginx
    ```

    The policy also keeps other workloads from setting the forwarded
    headers that the app trusts (see [Forwarded
    headers](#forwarded-headers)).

`kubectl exec` and `kubectl port-forward` don't go through the pod network
and are not affected. The policies don't block the probes: connections from
the pod's own node, where the kubelet runs them, are allowed.

## Server

The image serves the app with Gunicorn on port 8080 (see
[Server](https://trs-filer.readthedocs.io/en/latest/configuration/#server)).
The chart passes the settings in `trsFiler.gunicorn` to it (via
`GUNICORN_CMD_ARGS`); the defaults are the image's (one worker process with
4 threads, a timeout of 30 seconds, a graceful timeout of 20 seconds, and a
keep-alive of 100 seconds, longer than the upstream keep-alive timeout of
common ingress controllers: 60 seconds for ingress-nginx, 90 seconds for
Traefik). Rendering fails if `extraArgs` set `--bind`/`-b`, `--preload` or
`--graceful-timeout`. On shutdown, the app keeps serving for
`trsFiler.preStopSleepSeconds` (default 5) before Gunicorn stops, so that the
ingress controller stops sending requests to the pod first.

`trsFiler.extraEnv` (Kubernetes `EnvVar`s) and `trsFiler.extraEnvFrom`
(`EnvFromSource`s) add environment variables to the app's container, e.g.,
`FORWARDED_ALLOW_IPS` (see [Forwarded headers](#forwarded-headers)) or
settings from a Secret of your own; rendering fails for the variables that
the chart sets itself, and for secrets as literal values. Helm doesn't
restart the pods when a Secret changes, unless it is listed in
`trsFiler.rolloutOnSecrets` (which needs Helm to read the cluster, so not
with `helm template` or Argo CD); otherwise, restart them after changing one
(`kubectl rollout restart deploy/trs-filer -n <namespace>`).

`trsFiler.resources` sets the CPU and memory of the app: by default a
request of 256Mi and a limit of 384Mi memory. With the default Gunicorn
settings and request size limit (1 MiB), the app uses about 115 MB at rest
(worker about 90 MB, master about 25 MB) and peaked at about 175 MB in a
test with 12 concurrent registrations of about 1 MB each plus downloads and
listings (resident set sizes, which count shared pages twice); the request
covers that, and the limit leaves room for larger responses. Each further
Gunicorn worker loads the whole app, so add about 150Mi per worker to the
request and the limit before raising `workers`; more threads per worker or a
higher request size limit (`config.server.max_content_length`) need more.
`mongodb.resources` sets those of MongoDB (by default 512Mi).

## Several replicas

`trsFiler.replicas` (default: 1) sets the number of the app's pods. With
more than one, the chart renders a PodDisruptionBudget, so that voluntary
disruptions (e.g., node drains) evict at most one pod at once; set
`trsFiler.podDisruptionBudget.minAvailable` or `maxUnavailable` to change
that, or `enabled: false` to render none. Tools are kept in MongoDB, so
the pods share them. See [Several
replicas](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#several-replicas)
in FOCA's docs for the caveats. The chart has no autoscaler.

## Probes

- **App:** ready once it serves its Swagger UI (`/ga4gh/trs/v2/ui/`; it
  needs neither authentication nor the database; set `trsFiler.probePath`
  if the config disables the Swagger UI); up to 5 minutes are allowed for
  the start. `trsFiler.startupProbe`, `trsFiler.readinessProbe` and
  `trsFiler.livenessProbe` (Kubernetes probe specs) each replace a default
  entirely.
- **MongoDB:** ready once it accepts connections.

## MongoDB

### Version

The chart pins MongoDB (`mongodb.image`, default `mongo:7.0`, the version
that CI tests; MongoDB 8.0 refuses to start on Linux kernels 6.19 to 7.0.13,
cf. [SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)). Before
moving to 8.0, check the kernels of the nodes that MongoDB may run on (nodes
added later, e.g., by an autoscaler, must have compatible kernels too):

```bash
kubectl get nodes -o custom-columns=NODE:.metadata.name,KERNEL:.status.nodeInfo.kernelVersion
```

MongoDB only starts on data whose feature compatibility version (FCV) it
supports, so check the running version and the FCV before changing the
image of an existing database (with `mongosh`, or `mongo`, the old shell, in
images before 6.0):

```bash
kubectl exec deploy/trs-filer-mongodb -n <namespace> -- sh -c \
  '"$(command -v mongosh || echo mongo)" --quiet \
  -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --eval "printjson({version: db.version(), fcv: db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion})"'
```

(Without authentication, leave out `-u`, `-p` and
`--authenticationDatabase`; the same holds for the other `mongosh`,
`mongodump` and `mongorestore` commands of this page and the upgrade
notes.)

- **Upgrades** go one major version at a time (e.g., 6.0 → 7.0 → 8.0): set
  the image of the next version, wait for the rollout, then set the FCV to
  that version (e.g.,
  `db.adminCommand({setFeatureCompatibilityVersion: "7.0", confirm: true})`)
  before the next step.
- **Downgrades** are not supported by the `mongo` images (MongoDB Community
  Edition): keep the running major and minor version (as `db.version()`
  reports it, e.g., `mongodb.image: docker.io/library/mongo:8.2`), or dump
  the database (`mongodump`) and restore it (`mongorestore`) into a new,
  empty volume with the older version.

The MongoDB Deployment uses the `Recreate` strategy, as the data volume can
only be used by one pod: changing the image stops MongoDB, and an image that
can't read the data leaves it down until the image is changed back.

### Authentication

MongoDB requires credentials (`mongodb.auth.enabled`, by default `true`).
They come from an existing Secret in the release's namespace, named by
`mongodb.auth.existingSecret`, with four keys (see
[Installation](#installation)):

- `root-username` and `root-password`: MongoDB's root user (in the database
  `admin`), for administration (e.g., the commands in [Version](#version));
- `username` and `password`: the app user, with the role `readWrite` on the
  app's database, `trsStore`, only, in which it is created; the app
  connects as this user (FOCA's `MONGO_USERNAME` and `MONGO_PASSWORD`).
  `trsStore` also holds the rules of access control.

Without a Secret name, rendering fails. To run MongoDB without
authentication, set `mongodb.auth.enabled: false` explicitly; any pod that
can reach the MongoDB Service can then read and change the data (Helm's
notes after installing warn of it). Credentials never appear in values
files or ConfigMaps.

MongoDB creates both users when it starts with an empty volume (the root
user by its image's entrypoint, the app user by the init script of the
ConfigMap `<app>-mongodb-init-script`), and enforces authentication on every
start. Changing the Secret doesn't change the users: to change a password,
change it in MongoDB first (e.g.,
`db.getSiblingDB("trsStore").changeUserPassword("trs-filer", "<new
password>")` as the root user), then update the Secret and restart the app
(`kubectl rollout restart deploy/trs-filer -n <namespace>`); its requests to
the database fail until then. After changing the root user's password, also
restart MongoDB (`kubectl rollout restart deploy/trs-filer-mongodb -n
<namespace>`), whose environment the commands in this README use for the
root user's credentials. See [Deployment
notes](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#deployment-notes)
of the library chart for creating the users of an existing database.

### Persistence

MongoDB keeps its data in a PersistentVolumeClaim (`<app>-mongodb`;
`mongodb.persistence`: `size`, by default `1Gi`, `accessModes`,
`storageClass`, or an `existingClaim`). Helm keeps the claim, and with it
the database, when the release is uninstalled
(`mongodb.persistence.resourcePolicy: keep`); a new release of the same name
in the same namespace uses it again. To remove the data, delete the claim
after uninstalling the release (`kubectl delete pvc trs-filer-mongodb -n
<namespace>`; with the reclaim policy `Retain`, also delete its
PersistentVolume and the storage behind it with your storage provider).
With `mongodb.persistence.enabled: false` (e.g., for tests), the data is
lost when MongoDB's pod is replaced.

### External MongoDB

To use a MongoDB outside the release (e.g., a managed database), set
`mongodb.enabled: false` and its host (and port) in the config; rendering
fails without `config.db.host`:

```yaml
mongodb:
  enabled: false
  auth:
    # Secret with the keys `username` and `password` of the app user
    existingSecret: trs-filer-mongodb-credentials
config:
  db:
    host: mongodb.example.org
    port: 27017
```

The app authenticates as the app user against its database (`trsStore`), so
create that user there, with the `readWrite` role on `trsStore`, which
includes the right to create the indexes that the app creates on startup;
allow the app's pods to connect to the database.

## Upgrades

Change the values file (e.g., `config` for the config, `trsFiler.tag` for
the image of a chart from the repository) and upgrade the release, with the
chart of a release (or `deployment`, as when installing):

```bash
helm upgrade trs-filer trs-filer-{{ chart_version }}.tgz -n <namespace> \
    -f values-prod.yaml
```

Upgrade with the values file (`-f`), not with `--reuse-values`, which would
keep values that the chart no longer has, and without the defaults of the
new chart. The app's pods are replaced when the config changes. See
[Upgrading](https://trs-filer.readthedocs.io/en/latest/upgrading/) for the
changes of the app since the last deployed version.

### From earlier charts

The charts before the library chart (up to the one of 0.5.0 and those on
`dev` before it; with a config Job that wrote the ConfigMap) used other
values, resource names and selectors, and the database `trs-filer-db`. The
current chart renames the resources (see [Names and
labels](#names-and-labels); e.g., `mongodb-trs-filer` becomes
`trs-filer-mongodb`), changes the selectors of the Deployments, which can't
be changed in place, and uses the database `trsStore`, so **releases of
earlier charts can't be upgraded: uninstall them and install the current
chart, moving the data.** `helm upgrade` fails for releases with
Deployments of an earlier chart (only when Helm can query the cluster: not
in `helm template` or client-side dry runs).

Rendering fails for the values of earlier charts, which the current chart
would ignore:

| Earlier values | Now |
| --- | --- |
| `host_name` | `hostName` |
| `trs_filer` (e.g., `trs_filer.ingress`, `trs_filer.resources`) | `trsFiler`, with the same keys unless listed here |
| `trs_filer.config` | `config` |
| `trs_filer.image` (with the tag, e.g., `elixircloud/trs-filer:X.Y.Z`) | `trsFiler.image` and `trsFiler.tag` (or the image with the tag and an empty `trsFiler.tag`, see [Image](#image)) |
| `trs_filer.appName` (default `trs-filer`) | `fullnameOverride` (see [Names and labels](#names-and-labels)) |
| `trs_filer.forwardedAllowIps` (default `*`) | `FORWARDED_ALLOW_IPS` in `trsFiler.extraEnv` (see [Forwarded headers](#forwarded-headers)) |
| `apiServer` | none: the chart has no config Job |
| `mongodb.dbName` (default `trs-filer-db`) | none: the database is `trsStore` |
| `mongodb.volumeSize` | `mongodb.persistence.size` |

To keep the tools, dump the database before uninstalling and restore it
into the new release. The app is down from the first to the last step. The
commands are for the release `trs-filer` and the earlier charts' default
names (`trs-filer` and `mongodb-trs-filer`, from `trs_filer.appName`, and
the database `trs-filer-db`, from `mongodb.dbName`); replace them if yours
differ:

1. Stop the app, so that the data doesn't change during the dump:

    ```bash
    kubectl scale deploy/trs-filer -n <namespace> --replicas=0
    ```

2. Dump the app's database to a local file, and check that MongoDB can read
   the dump; continue only if `Dump OK` is printed:

    ```bash
    kubectl exec deploy/mongodb-trs-filer -n <namespace> -- sh -c 'mongodump --quiet \
      -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
      --authenticationDatabase admin --db trs-filer-db --archive' \
      > trs-filer-db.archive \
    && kubectl exec -i deploy/mongodb-trs-filer -n <namespace> -- sh -c 'mongorestore \
      --dryRun -u "$MONGO_INITDB_ROOT_USERNAME" \
      -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin \
      --archive' < trs-filer-db.archive \
    && echo "Dump OK"
    ```

3. Uninstall the release (`helm uninstall trs-filer -n <namespace>`) and
   update the values file (see the table above). The claim of the earlier
   chart (`mongodb-trs-filer`) is kept, with the data: keep it until the new
   release serves the tools. The Secret with MongoDB's credentials can be
   reused (the new release creates the users in its new volume); releases
   that ran without authentication create it first (see
   [Installation](#installation)). Set `mongodb.image` to the version of the
   earlier release if it differs (see [Version](#version)).

4. Install the current chart (see [Installation](#installation)), stop its
   app again, so that it doesn't write during the restore, and wait for
   MongoDB:

    ```bash
    kubectl scale deploy/trs-filer -n <namespace> --replicas=0
    kubectl rollout status deploy/trs-filer-mongodb -n <namespace>
    ```

5. Restore the dump into `trsStore`, replacing the collections that the app
   has created, then start the app (with the number of `trsFiler.replicas`):

    ```bash
    kubectl exec -i deploy/trs-filer-mongodb -n <namespace> -- sh -c \
      'mongorestore --quiet --drop --archive \
      --nsFrom "trs-filer-db.*" --nsTo "trsStore.*" \
      -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
      --authenticationDatabase admin' < trs-filer-db.archive
    kubectl scale deploy/trs-filer -n <namespace> --replicas=1
    ```

6. Check that the app lists the tools (e.g., `curl -s
   'https://trs.example.org/ga4gh/trs/v2/tools?limit=1'`), then delete the
   earlier claim (`kubectl delete pvc mongodb-trs-filer -n <namespace>`) and
   the dump.
