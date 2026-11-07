# TRS filer Helm chart

> **Warning:** TRS-Filer has no authentication yet: anyone who can reach the
> API can register, replace and delete tools and tool classes. Allow `POST`,
> `PUT` and `DELETE` only from trusted clients, at the ingress controller or
> the OpenShift router (see [Ingress and Route](#ingress-and-route)) or at a
> proxy in front of the cluster (see
> [Access control](https://trs-filer.readthedocs.io/en/latest/access-control/)).
> The chart restricts nothing by default. Tokens for writes are planned
> ([#7](https://github.com/elixir-cloud-aai/trs-filer/issues/7)).

## Quick start

Set `host_name` (see [Values](#values)): it is **required**, the chart has no
useful default, and the configuration Job fails (exit 1) on the empty one.

MongoDB requires authentication: create a Secret with its credentials in the
namespace first, and pass its name in `mongodb.auth.existingSecret` (see
[Authentication](#authentication)); otherwise, rendering the chart fails.
E.g., with random passwords:

```bash
kubectl create namespace namespace
kubectl create secret generic trs-filer-mongodb-credentials -n namespace \
    --from-literal=root-username=root \
    --from-literal=root-password="$(openssl rand -hex 24)" \
    --from-literal=username=trs-filer \
    --from-literal=password="$(openssl rand -hex 24)"
```

### Install a release

Install the chart attached to a release (`trs-filer-{{ chart_version }}.tgz`
of the latest release, `{{ version }}`), which sets the release's image. It is
signed and has a build attestation: download and verify it before you
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
helm install trs-filer trs-filer-{{ chart_version }}.tgz -n namespace \
    --set host_name=trs.example.org \
    --set mongodb.auth.existingSecret=trs-filer-mongodb-credentials
```

`namespace` is the name of the namespace where TRS-Filer should be
installed (created above, with the Secret), and
`trs-filer` could be any name: it is referenced later for upgrading or
uninstalling. Set further values with `--set` or with a file
(`-f my-values.yaml`; `helm show values trs-filer-{{ chart_version }}.tgz`
prints the defaults).

### Install from source

To install the chart of a checkout of the repository (e.g., the branch `dev`,
whose default image is `elixircloud/trs-filer:latest`), edit `values.yaml` or
pass your values as above, and run this from the `deployment` folder:

```bash
helm install trs-filer . -n namespace \
    --set host_name=trs.example.org \
    --set mongodb.auth.existingSecret=trs-filer-mongodb-credentials
```

## Values

The values of `values.yaml`; the sections below describe them.

| Value | Default | Description |
| --- | --- | --- |
| `host_name` | `""` | **Required.** Host name that the app serves (the app advertises `https://<host_name>`, so serve HTTPS: see `trs_filer.ingress.https` and [Ingress and Route](#ingress-and-route)), used by the Ingress, the Route and the configuration Job. |
| `apiServer` | `kubernetes.default.svc:443` | Address of the Kubernetes API server, which the configuration Job writes the ConfigMap to. |
| `trs_filer.image` | `elixircloud/trs-filer:latest` | Image of the app (released charts set the release's image). |
| `trs_filer.appName` | `trs-filer` | Name of the app's Deployment and Service; names the other resources (e.g., `mongodb-<appName>`). Don't change it for an installed release (see [Persistence](#persistence)). |
| `trs_filer.forwardedAllowIps` | `"*"` | Addresses or networks (comma-separated, or a list) whose `X-Forwarded-*` headers the app trusts; `*` for every address (see [Forwarded headers](#forwarded-headers)). |
| `trs_filer.resources` | 100m CPU; 256Mi memory request, 384Mi limit | CPU and memory of the app (see [Resources](#resources)). |
| `trs_filer.podSecurityContext` | non-root, `RuntimeDefault` seccomp | Security context of the pods of the app and the configuration Job (see [Security contexts](#security-contexts)). |
| `trs_filer.securityContext` | no privilege escalation, no capabilities, read-only root file system | Security context of their containers. |
| `trs_filer.tmpSizeLimit` | `64Mi` | Size limit of their `emptyDir` at `/tmp`; `null` for none. |
| `trs_filer.networkPolicy.enabled` | `false` | Create a NetworkPolicy that lets only `ingressFrom` connect to the app (see [Network policies](#network-policies)). |
| `trs_filer.networkPolicy.ingressFrom` | `[]` | NetworkPolicy peers allowed to connect to the app; required if enabled. |
| `trs_filer.ingress.enabled` | `true` | Create an Ingress (see [Ingress and Route](#ingress-and-route)). |
| `trs_filer.ingress.className` | `""` | Ingress class; the cluster's default class if empty. |
| `trs_filer.ingress.annotations` | `{}` | Annotations of the Ingress; `null` removes one of the chart's. |
| `trs_filer.ingress.https.enabled` | `false` | Request a certificate from cert-manager and serve HTTPS. |
| `trs_filer.ingress.https.issuer` | `letsencrypt-prod` | cert-manager ClusterIssuer for `https`. |
| `trs_filer.route.enabled` | `true` | Create an OpenShift Route if the Ingress is disabled and the cluster serves Routes. |
| `trs_filer.route.annotations` | `{}` | Annotations of the Route; `null` removes one. |
| `mongodb.image` | `docker.io/library/mongo:7.0` | MongoDB image (see [MongoDB](#mongodb)). |
| `mongodb.imagePullPolicy` | `Always` | Pull policy of the MongoDB image. |
| `mongodb.dbName` | `""` | Name of the app's database; `trs-filer-db` if empty. |
| `mongodb.auth.enabled` | `true` | Require credentials (see [Authentication](#authentication)). |
| `mongodb.auth.existingSecret` | `""` | **Required** with authentication: name of the Secret with the keys `root-username`, `root-password`, `username` and `password`. |
| `mongodb.volumeSize` | `1Gi` | Size of the PersistentVolumeClaim with the data (see [Persistence](#persistence)). |
| `mongodb.resources` | 200m CPU; 512Mi memory | CPU and memory of MongoDB (request and limit). |
| `mongodb.podSecurityContext` | non-root user and group 999, `fsGroup` 999 (applied on a mismatch only), `RuntimeDefault` seccomp | Security context of MongoDB's pod (see [Security contexts](#security-contexts)). |
| `mongodb.securityContext` | no privilege escalation, no capabilities, read-only root file system | Security context of MongoDB's container. |
| `mongodb.tmpSizeLimit` | `64Mi` | Size limit of MongoDB's `emptyDir` at `/tmp`; `null` for none. |
| `mongodb.networkPolicy.enabled` | `true` | Create a NetworkPolicy that lets only the app connect to MongoDB (see [Network policies](#network-policies)). |

## Security notes

- **No authentication in the API**, see the warning at the top.
- **MongoDB requires credentials** by default (see
  [Authentication](#authentication)); the app connects as a user with
  access to its database only. Its NetworkPolicy (`mongodb.networkPolicy`,
  see [Network policies](#network-policies)) also lets only the app's pods
  connect to it, in clusters that enforce NetworkPolicies; otherwise, every
  pod in the cluster reaches its Service (`mongodb-<appName>`, port 27017;
  the chart exposes it nowhere else). With `mongodb.auth.enabled: false`,
  every pod that reaches it can read and change the data.
- **The configuration Job has a ServiceAccount with rights in the
  namespace.** Its ServiceAccount (`<appName>-configurer`) is bound
  (RoleBinding `<appName>-configurer`) to the Role `<appName>-configurer`,
  which allows only what the Job does: read and patch the ConfigMap
  `app-config-<appName>`, and list and delete pods, to restart the app. The
  pod rights cover every pod in the namespace (pod names are generated, so
  the Role can't name them), though the Job deletes only the app's pods
  (label `app: <appName>`). It
  runs on every install and upgrade; the chart needs permission to create
  these resources, and the rights exist as long as the release does. If
  reading or patching the ConfigMap or listing pods fails (e.g., the API
  server refuses it in a copy of the chart that changes the ConfigMap's
  name), the Job fails (exit code 7, 8 or 9 of `update-config-map.sh`);
  a failed pod deletion doesn't fail it. This stays until the chart uses FOCA's library
  chart ([#135](https://github.com/elixir-cloud-aai/trs-filer/issues/135)).
- **By default, the app trusts `X-Forwarded-*` headers from every address**
  (`trs_filer.forwardedAllowIps: "*"`), so that links in responses keep
  `https` behind the ingress or route that terminates TLS. Every workload
  that can reach the app's Service or pod can then set these headers, and
  so change the URLs in responses. Narrow the value to the addresses of
  the ingress controller or router (see [Forwarded
  headers](#forwarded-headers)), don't expose the Service or the pod to
  clients directly, and restrict access to them to the ingress controller
  or router, e.g., with `trs_filer.networkPolicy` (see [Network
  policies](#network-policies)).

## Security contexts

All pods run as non-root users, without privilege escalation or
capabilities, with the `RuntimeDefault` seccomp profile and a read-only root
file system, as the Pod Security Standard "restricted" requires (e.g., for
namespaces labelled `pod-security.kubernetes.io/enforce: restricted`):

- The app and the configuration Job (`trs_filer.podSecurityContext`,
  `trs_filer.securityContext`) run as the image's user (1000); MongoDB
  (`mongodb.podSecurityContext`, `mongodb.securityContext`) runs as the
  image's user `mongodb` (999), and its data volume belongs to its group
  (`fsGroup: 999`), so that MongoDB can write to it. This needs storage
  that applies `fsGroup` (most dynamically provisioned volumes do; e.g.,
  `hostPath` and some CSI drivers don't): otherwise, MongoDB can't write to
  a new volume and doesn't start. For such storage, prepare the volume's
  ownership (user 999) yourself, or let MongoDB's entrypoint start as root
  and switch to its user, as before (`mongodb.podSecurityContext: null`,
  `mongodb.securityContext: null`; not allowed under "restricted").
- Temporary files go to `emptyDir`s at `/tmp`, limited by
  `trs_filer.tmpSizeLimit` and `mongodb.tmpSizeLimit` (the pod is evicted
  if it exceeds the limit); MongoDB also gets one at `/data/configdb`.
- On OpenShift (if the cluster serves `security.openshift.io/v1`), the
  chart sets no `runAsUser`, `runAsGroup` or `fsGroup`, as OpenShift
  assigns them from the namespace's range.

The values are maps: values files are merged into them, and `null` removes
a key (e.g., `mongodb.podSecurityContext.runAsUser: null`).

## Network policies

The chart creates NetworkPolicies, which clusters with a network plugin
that supports them enforce (others ignore them):

- **MongoDB** (`mongodb-<appName>`, `mongodb.networkPolicy.enabled`, on by
  default): only the app's pods (label `app: <appName>`) may connect to
  MongoDB, on port 27017. Disable it if you manage policies yourself, or
  if other workloads (e.g., backups) must connect.
- **The app** (`<appName>`, `trs_filer.networkPolicy.enabled`, off by
  default): only the peers in `trs_filer.networkPolicy.ingressFrom` may
  connect to the app, on port 8080. The peers depend on the cluster, so
  there are no defaults, and rendering fails if the policy is enabled
  without any (which would allow all sources). E.g., for ingress-nginx in
  the namespace `ingress-nginx`:

    ```yaml
    trs_filer:
      networkPolicy:
        enabled: true
        ingressFrom:
          - namespaceSelector:
              matchLabels:
                kubernetes.io/metadata.name: ingress-nginx
    ```

    On OpenShift, the router's pods are in namespaces labelled
    `policy-group.network.openshift.io/ingress: ""`. The policy also keeps
    other workloads from setting the forwarded headers that the app trusts
    (see [Security notes](#security-notes)).

The policies restrict incoming connections only. Kubernetes combines all
NetworkPolicies that select a pod: if other policies in the namespace
(e.g., a namespace-wide "allow" policy) select the app's or MongoDB's
pods, the sources they allow can connect too. Check them with
`kubectl get networkpolicy -n <namespace>`, and keep their selectors off
these pods.

## Resources

`trs_filer.resources` sets the CPU and memory of the app: by default a
request of 256Mi and a limit of 384Mi memory. With the image's Gunicorn
defaults (one worker with four threads) and the default request size limit
(1 MiB), the app uses about 115 MB at rest (worker about 90 MB, master
about 25 MB) and peaked at about 175 MB in a test with 12 concurrent
registrations of about 1 MB each plus downloads and listings (resident set
sizes, which count shared pages twice); the request covers that, and the
limit leaves room for larger responses. With the request below the limit,
the pod has the QoS class `Burstable`; set both to the same value (e.g.,
384Mi) for `Guaranteed`.

Each further Gunicorn worker loads the whole app, so add about 150Mi per
worker to the request and the limit; more threads per worker or a higher
request size limit (`server.max_content_length`) need more. The chart has no
value for Gunicorn's settings (`GUNICORN_CMD_ARGS`, see
[Server](https://trs-filer.readthedocs.io/en/latest/configuration/#server))
yet: add the variable to the app's Deployment in a copy of the chart (see
[Configuration](#configuration)), until the chart uses FOCA's library chart
([#135](https://github.com/elixir-cloud-aai/trs-filer/issues/135)).
`mongodb.resources` sets those of MongoDB (by default 512Mi).

## Ingress and Route

The chart exposes the app for `host_name` via an Ingress
(`trs_filer.ingress.enabled`, by default `true`) or, if it is disabled and
the cluster serves Routes, an OpenShift Route (`trs_filer.route.enabled`, by
default `true`; with TLS at the router). With neither, nothing exposes the
app (NOTES.txt warns of it): expose its Service (`<appName>`, port 8080)
yourself, e.g., with a Route or HTTPRoute of your own. The Ingress routes
all paths (`/`) to the app and is configured with:

- `className` sets the Ingress class (`spec.ingressClassName`; default: the
  cluster's default class);
- `annotations` sets annotations, e.g., for the ingress controller; they
  take precedence over those that the chart sets for `https`, and `null`
  removes one of these;
- `https.enabled` requests a certificate from cert-manager (via the
  ClusterIssuer `https.issuer`) and serves HTTPS with it. Without it, the
  Ingress serves plain HTTP: terminate TLS in front of the cluster then, as
  the app advertises `https://<host_name>` URLs (e.g., the `url` of tools).

The chart sets no annotations for particular ingress controllers. Restrict
the methods that change data (`POST`, `PUT`, `DELETE`) to trusted clients
with the means of your ingress controller or proxy. For example (an example
only, adapt it to your setup), with ingress-nginx, which allows them only
from the network `192.0.2.0/24`:

```yaml
trs_filer:
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
`externalTrafficPolicy: Local` or the PROXY protocol (with
`externalTrafficPolicy: Cluster`, clients appear with the addresses of the
nodes). If the controller trusts forwarded headers (`use-forwarded-headers`),
limit them to your proxies (`proxy-real-ip-cidr`, by default `0.0.0.0/0`),
or anyone can claim an allowed address in `X-Forwarded-For`. A controller
that doesn't allow snippets ignores the annotation (or its admission webhook
rejects the Ingress), leaving writes open: check with a `POST` from an
untrusted address that writes are refused (`403`).
Recent versions of ingress-nginx disable snippet annotations by default (the
controller must allow them, `allow-snippet-annotations`, and annotations of
their risk level, `annotations-risk-level: Critical`), as they let anyone
who can create Ingresses change the controller's configuration; check that
this is acceptable in your cluster. ingress-nginx is also retired (no
releases or security fixes after March 2026): with other controllers or the
Gateway API, use their means to restrict methods or clients, or restrict
them at a proxy in front of the cluster.

### OpenShift Route

The Route (`<appName>-route`) routes all paths to the app, with TLS at the
router, which redirects HTTP to HTTPS. `trs_filer.route.annotations` sets
its annotations, e.g., for the router's rate limits
(`haproxy.router.openshift.io/rate-limit-connections: "true"` with, e.g.,
`haproxy.router.openshift.io/rate-limit-connections.rate-http: "100"`);
quote numbers, and `null` removes an annotation. The chart sets none, so
the Route restricts nothing by default. The OpenShift router can't
restrict methods, only clients: to allow only trusted clients (for all
methods, also `GET`; an example only, adapt it to your setup), e.g., from
the network `192.0.2.0/24`:

```yaml
trs_filer:
  ingress:
    enabled: false
  route:
    annotations:
      haproxy.router.openshift.io/ip_allowlist: 192.0.2.0/24
```

Separate several networks or addresses with spaces; OpenShift before 4.14
uses `haproxy.router.openshift.io/ip_whitelist`. The router checks the
source address that it sees, which is the client's only if it gets
through a load balancer in front of it (e.g., with the PROXY protocol or
`externalTrafficPolicy: Local`); otherwise, it is that of the load
balancer or a node. To keep reads public and restrict only writes,
restrict them at a proxy in front of the router. Check with a `POST` from
an untrusted address that writes are refused.

### Forwarded headers

The ingress controller or router terminates TLS and forwards requests to
the app via HTTP, with `X-Forwarded-*` headers. The app trusts these
headers from the addresses in `trs_filer.forwardedAllowIps` (Gunicorn's
`FORWARDED_ALLOW_IPS`), so that the links in its responses (e.g., the
`next_page`, `last_page` and `self_link` headers of tool listings) keep
`https`. By default (`*`), it trusts them from every address, which works
with any ingress controller or router, but lets every workload that can
reach the app's Service or pod set the scheme of these links (and their
path, via Gunicorn's `SCRIPT_NAME` header). The host of the links comes from the `Host` header, which
this value doesn't cover: every client that reaches the pod sets it.

Narrow it to the addresses that the ingress controller or router connects
from, as addresses or networks in CIDR notation (network addresses, e.g.,
`192.0.2.0/24`, not `192.0.2.1/24`), comma-separated or as a list, e.g.,
the nodes' subnet if the controller runs in the host network:

```yaml
trs_filer:
  forwardedAllowIps:
    - 192.0.2.0/24
```

A network trusts every address in it: the pod network of the cluster
(e.g., `10.128.0.0/14` on OpenShift) contains every pod, so it protects
little. Pods get new addresses when they are rescheduled, so list
networks rather than pod addresses, and restrict who can reach the app's
pods with NetworkPolicies. An invalid entry stops the app (Gunicorn exits
on startup); an empty value, entries with spaces inside, or a value that
isn't a string or a list of strings fail rendering. Check afterwards that a
listing through the Ingress or Route still gives `https` links (e.g.,
`curl -sI 'https://trs.example.org/ga4gh/trs/v2/tools?limit=1'` and its
`self_link` header). With an address that doesn't match, the links get
`http`.

## Configuration

The chart can't configure the app yet, apart from the public URL
(`https://<host_name>:443`), the MongoDB host and the database (the latter
via `MONGO_DBNAME` on the app's Deployment): a Job
(`configmap-job-<appName>-<revision>`, run on every install and upgrade)
renders the public URL and the MongoDB host into the base config of the
image and writes the result to
the ConfigMap `app-config-<appName>`, the app's config overlay
(`FOCA_CONFIG_OVERLAY`), replacing it as a whole. `values.yaml` has no value
for the config, and changes to the ConfigMap are lost on the next upgrade.
So chart deployments serve the **placeholder service info** of the base
config (`id: org.example.trs-filer`, organization `Example Organization`),
and FOCA warns of it on startup; other settings (e.g., `custom.remote_files`,
the identifier character sets or `custom.toolclass.validation`, see
[Configuration](https://trs-filer.readthedocs.io/en/latest/configuration/))
keep their defaults. The chart will take an overlay as a value once it uses
FOCA's library chart
([#135](https://github.com/elixir-cloud-aai/trs-filer/issues/135)).

Until then, deploy a copy of the chart with a second overlay file, which
FOCA merges after the first one (paths in `FOCA_CONFIG_OVERLAY` are
separated by `:`); leave out the settings that the Job sets
(`custom.service` and `db.host`):

1. Add a ConfigMap with your overlay, e.g., the service info, as
   `templates/trs-filer-config-local.yaml`:

    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: app-config-local-{{ .Values.trs_filer.appName }}
    data:
      config.yaml: |
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

2. In `templates/trs-filer-deploy.yaml`, append its path to
   `FOCA_CONFIG_OVERLAY`, and mount it there:

    ```yaml
              - name: FOCA_CONFIG_OVERLAY
                value: /etc/trs-filer/config.yaml:/etc/trs-filer/local.yaml
    # ...
            volumeMounts:
            # ...
            - mountPath: /etc/trs-filer/local.yaml
              name: config-local
              subPath: config.yaml
    # ...
          volumes:
          # ...
          - configMap:
              name: app-config-local-{{ .Values.trs_filer.appName }}
            name: config-local
    ```

3. Install or upgrade the release from the copy. Files mounted with
   `subPath` aren't updated in running pods, so restart the app after
   changing the overlay (`kubectl rollout restart deploy/<appName> -n
   namespace`; the app's Deployment is named after `trs_filer.appName`).

## Upgrades

If you need to change any parameter of the deployment, the procedure is similar to installing:

1. Edit `values.yaml` (or your values file) with the new configuration you want to apply. For example, if you want to change the image of trs-filer, change `trs_filer.image`.

2. Upgrade the Helm chart. Run this from the `deployment` folder, or with the
   `.tgz` of a release instead of `.`. `helm upgrade` applies the chart's
   defaults for values you don't pass again (`host_name` would be empty, and
   the configuration Job fails), so pass the same values as when installing,
   e.g., your values file (`-f my-values.yaml`) or `--set host_name=...`.
   `--reuse-values` reuses the release's values as they are, including the
   chart's defaults at the time, so values that a newer chart adds or
   changes (e.g., the [Security contexts](#security-contexts) and [Network
   policies](#network-policies)) don't take effect; pass your values file
   instead, or use `--reset-then-reuse-values` (Helm 3.14 or later), which
   applies the new chart's defaults with your earlier values on top:
```
helm upgrade trs-filer . -n namespace -f my-values.yaml
```
`namespace` is the name of the namespace where the cluster was installed.
`trs-filer` is the name given when installing. In order to see the correct name, do a `helm ls -n namespace`.

Releases installed from the chart in the repository before (from the tag
`v0.3.0` or from `dev`) may need more steps, or the upgrade **deletes the
database** or leaves MongoDB unable to start: see [Helm
chart](https://trs-filer.readthedocs.io/en/latest/upgrading/#helm-chart) in
the upgrade notes before upgrading them.

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
supports, so check the running version and the FCV before changing the image
of an existing database (with `mongosh`, or `mongo`, the old shell, in
images before 6.0):

```bash
kubectl exec deploy/mongodb-trs-filer -n namespace -- sh -c \
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
cannot read the data leaves it down until the image is changed back.

### Authentication

MongoDB requires credentials (`mongodb.auth.enabled`, by default `true`).
They come from an existing Secret in the release's namespace, named by
`mongodb.auth.existingSecret`, with four keys:

- `root-username` and `root-password`: MongoDB's root user (in the
  database `admin`), for administration (e.g., the commands in
  [Version](#version)).
- `username` and `password`: the app user, with the role `readWrite` on
  the app's database (`mongodb.dbName`, by default `trs-filer-db`) only, in
  which it is created; the app connects as this user (FOCA's
  `MONGO_USERNAME` and `MONGO_PASSWORD`).

Create the Secret before installing (see [Quick start](#quick-start));
without a Secret name, rendering the chart fails. To run MongoDB without
authentication, set `mongodb.auth.enabled: false` explicitly. Credentials
never appear in values files or ConfigMaps.

MongoDB creates both users when it starts with an empty volume (the root
user by its image's entrypoint, the app user by the init script
`create-app-user.js` of the ConfigMap `mongo-init-script-<appName>`), and
enforces authentication on every start. Changing the Secret doesn't change
the users: to change a password, change it in MongoDB first (e.g.,
`db.getSiblingDB("trs-filer-db").changeUserPassword("trs-filer", "<new
password>")` as the root user), then update the Secret and restart the app
(`kubectl rollout restart deploy/trs-filer -n namespace`); its requests to
the database fail until then. Changing `mongodb.dbName` of an installed
release needs a user in the new database too.

**Existing databases without authentication** (installed by earlier
charts, or with `mongodb.auth.enabled: false`): MongoDB enforces
authentication as soon as the chart enables it, but creates no users on
the existing volume, so the app can't connect. Create the users first,
while authentication is still off:

1. Create the Secret (see [Quick start](#quick-start)).
2. Create the users in the running MongoDB, with the credentials of the
   Secret; the commands read them from the Secret, so that they don't
   appear in the shell's history:

    ```bash
    kubectl get secret trs-filer-mongodb-credentials -n namespace -o json \
      | jq -r '.data | map_values(@base64d)
          | "db.getSiblingDB(\"admin\").createUser({user: \(."root-username" | tojson), pwd: \(."root-password" | tojson), roles: [\"root\"]});
             db.getSiblingDB(\"trs-filer-db\").createUser({user: \(.username | tojson), pwd: \(.password | tojson), roles: [{role: \"readWrite\", db: \"trs-filer-db\"}]});"' \
      | kubectl exec -i deploy/mongodb-trs-filer -n namespace -- mongosh --quiet
    ```

    (With another `mongodb.dbName`, replace `trs-filer-db`.)
3. Upgrade the release with `mongodb.auth.existingSecret` set (and
   `mongodb.auth.enabled` not set to `false`).

If the root user exists but the app user is missing (e.g., because the
first start was interrupted), log in as the root user and create only the
app user:

```bash
kubectl exec -it deploy/mongodb-trs-filer -n namespace -- sh -c 'mongosh \
  -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin'
```

```javascript
db.getSiblingDB("trs-filer-db").createUser({user: "trs-filer", pwd: "<password>", roles: [{role: "readWrite", db: "trs-filer-db"}]})
```

### Persistence

MongoDB keeps its data in the PersistentVolumeClaim `mongodb-<appName>` (by
default `mongodb-trs-filer`, of `mongodb.volumeSize`). The claim is
annotated with `helm.sh/resource-policy: keep`, so Helm keeps it, and the
database, when the release is uninstalled; installing a release with the
same name and `trs_filer.appName` in the same namespace uses it again (Helm
refuses to install a release of another name over it). Delete it by hand to
remove the data (`kubectl delete pvc mongodb-trs-filer -n namespace`; with
the reclaim policy `Retain`, also delete its PersistentVolume and the
storage behind it with your storage provider).

The claim's name follows `trs_filer.appName`: changing it for an installed
release starts MongoDB on a new, empty claim (the old one is kept). Don't
change it, or move the data with `mongodump` and `mongorestore` (see [Helm
chart](https://trs-filer.readthedocs.io/en/latest/upgrading/#helm-chart) in
the upgrade notes).
