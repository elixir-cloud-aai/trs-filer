# Access control

TRS-Filer has no authentication or authorization yet: all endpoints,
including those that register, change and delete tools, versions and tool
classes (see [Registering tools](api.md#registering-tools)), are open to
anybody who can reach the API. Until it has its own access control, restrict
access in front of it:

- Docker Compose publishes the app on the host's loopback interface
  (`127.0.0.1:8080`) only; publish it on other interfaces only behind a
  reverse proxy that restricts access.
- In deployments, let the reverse proxy or ingress controller allow only
  `GET` requests (and `HEAD`, `OPTIONS`) from the public, and the other
  methods only from trusted clients (e.g., by IP address or with
  authentication at the proxy).
- Such restrictions apply only to requests that pass the proxy or ingress
  controller. With the default values of the Helm chart
  (`trs_filer.networkPolicy.enabled: false`), every pod in the cluster can
  call the app's Service (`<appName>`, port 8080) directly, with all
  methods, set `X-Forwarded-*` headers, which change the scheme of the
  links in responses (and, via the `SCRIPT_NAME` header, their path;
  `trs_filer.forwardedAllowIps: "*"`), and set the
  `Host` header, which changes their host. To
  let only the ingress controller or router connect, enable
  `trs_filer.networkPolicy` with their pods or namespace in
  `trs_filer.networkPolicy.ingressFrom`, in a cluster whose network plugin
  enforces NetworkPolicies, and narrow `trs_filer.forwardedAllowIps` (see
  [Security notes](deployment.md#security-notes) and [Network
  policies](deployment.md#network-policies)).

See your proxy's documentation for how to restrict methods and clients. The
Helm chart's Ingress or OpenShift Route applies no such restrictions by
default; the Ingress takes annotations for the ingress controller, the
Route for the OpenShift router (see [Ingress and
Route](deployment.md#ingress-and-route), with examples for ingress-nginx and
the router).

Who may add tool classes is configured (see [Adding tool
classes](configuration.md#adding-tool-classes)); until TRS-Filer has users
and admins, it supports only mode `open`, in which anybody who may register
tools may add tool classes, too.

The API specification declares the read operations of TRS (the `GET`
endpoints of [GA4GH TRS endpoints](api.md#ga4gh-trs-endpoints)) and the
service info public (`security: []`), and TRS's security scheme `BEARER` as
an HTTP bearer scheme (see [Supported TRS
version](api.md#supported-trs-version)). A deployment can require a token
for reads with a [patch of the
specification](https://foca.readthedocs.io/en/latest/configuration/api/#patching-specifications)
in a config overlay that sets `security: [{BEARER: []}]` on the operations,
together with FOCA's token validation for the scheme
(`add_security_fields`, see FOCA's
[authentication](https://foca.readthedocs.io/en/latest/authentication/)),
e.g., for `GET /tools`:

```yaml
api:
  specs:
    trs:
      add_security_fields:
        x-bearerInfoFunc: foca.security.auth.validate_token
      patches:
        - paths:
            /tools:
              get:
                security:
                  - BEARER: []
```

FOCA then validates the tokens as configured in `security.auth`.

Access tokens for writes and ownership of tools are planned (see the [issue
tracker](https://github.com/elixir-cloud-aai/trs-filer/issues)); this page
will describe them.
