# Access control

Tools, their versions and files, and tool classes can be read by anyone,
unless the deployment [requires login for
reads](#requiring-login-for-reads). Writing, i.e., registering, changing and
deleting tools, versions and tool classes (see [Registering
tools](api.md#registering-tools)), requires an access token of an OpenID
Connect provider that the deployment trusts (see
[Authentication](#authentication)), of a user with the role `admin` (see
[Admins](#admins)). The identity provider, its claims and the groups mapped
to roles are deployment configuration, without defaults (see [Deployment
configuration](configuration.md#deployment-configuration)). Authentication
and access control are implemented with
[FOCA](https://foca.readthedocs.io/en/latest/access-control/), as in [Cloud
Registry](https://cloud-registry.readthedocs.io/en/latest/access-control/);
see the `security` section of the
[configuration](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/config.yaml).

## Authentication

Read operations (the `GET` endpoints of [GA4GH TRS
endpoints](api.md#ga4gh-trs-endpoints)), the service info, the API
specification (`/ga4gh/trs/v2/openapi.json`) and the Swagger UI
(`/ga4gh/trs/v2/ui/`) are public by default (see [Requiring login for
reads](#requiring-login-for-reads)); they ignore tokens, also invalid ones.
All write operations (`POST`, `PUT` and `DELETE`) require an access token of
a trusted issuer, sent as a bearer token:

```bash
curl -X POST "http://localhost:8080/ga4gh/trs/v2/tools" \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d @tool.json
```

Requests without a valid token are rejected with `401 Unauthorized` and a
Bearer challenge (`WWW-Authenticate: Bearer`, RFC 6750; with
`error="invalid_token"` for invalid tokens), before their body is validated;
requests with a valid token, but without the required role, with `403
Forbidden`, after their body is validated (invalid bodies get `400 Bad
Request` first). Both are [problem details](api.md#errors).

Tokens are obtained by logging in with the identity provider through an app
registered as its client (OpenID Connect), e.g., a portal or gateway, or a
client of your own for scripts. TRS-Filer accepts tokens only:

- that are access tokens as per [RFC
  9068](https://www.rfc-editor.org/rfc/rfc9068) (`typ` header `at+jwt`);
  other tokens, such as ID tokens, are rejected;
- of the issuers in `security.auth.issuers` (none by default: each
  deployment sets its identity provider, and the app refuses to start
  without one);
- for the client IDs in `security.auth.audience` (the `aud` claim), which each
  deployment sets to the apps that call it (see
  [Configuration](configuration.md#deployment-configuration)); the Docker
  Compose setup accepts tokens for any audience;
- that haven't expired and are signed with a key of the issuer (RS256).

TRS-Filer reads the user's group memberships from the group claim
(`security.access_control.claim_groups`, needed for the [admin
role](#admins)). Claims in `security.auth.userinfo_claims` are read from the
identity provider's user info endpoint with the token, for identity
providers that don't put them in access tokens, so the token must be allowed
to release them (e.g., request the corresponding scopes when logging in).
Tokens are validated by
[FOCA](https://foca.readthedocs.io/en/latest/authentication/).

FOCA's service clients (`security.auth.service_clients`,
`security.auth.on_behalf_of_header`) are not supported: the app refuses to
start with them, as requests of clients (or of the users they name) would
need roles of their own on tools.

For local development without an identity provider, authentication can be
disabled with a config overlay (see [Running without
authentication](development.md#running-without-authentication)); never do
this in deployments.

## Admins

Members of the groups that the deployment maps to the role `admin`
(`security.access_control.group_mapping`) are **admins**: they can do
everything, i.e., register, change and delete all tools, versions and tool
classes. E.g., with the group claim `groups`:

```yaml
security:
    access_control:
        claim_groups: groups
        group_mapping:
            trs-admins: admin
```

The app refuses to start without a group mapped to `admin`
(`security.access_control.require_admin`, FOCA), unless a deployment sets
`require_admin: false` (as the Docker Compose setup does): then nobody can
write. On startup, FOCA logs the groups mapped to `admin`.

Until tools have owners
([#86](https://github.com/elixir-cloud-aai/trs-filer/issues/86)), only admins
may write, so that no user can change the tools of others. Tool classes are
a vocabulary that all tools share, so changing them stays with admins, too
(see [Adding tool classes](configuration.md#adding-tool-classes)). Unlike
Cloud Registry, TRS-Filer has no admin mode yet: admins act as admins on
every request, without the header `X-Request-Roles`.

To let other users write, map a group to a role of your own and give the role
write rules in a config overlay, e.g., for editors who may register, change
and delete all tools and versions:

```yaml title="editors.yaml"
security:
    access_control:
        group_mapping:
            trs-admins: admin
            trs-editors: editor
        policies:
            editors-register-tools: [p, editor, /ga4gh/trs/v2/tools, POST]
            editors-change-tools: [p, editor, "/ga4gh/trs/v2/tools/*", "(POST)|(PUT)|(DELETE)"]
```

Editors can then change all tools, also those that others registered, and
add tool classes by registering tools with new ones (unless
`custom.toolclass.validation` is true), but not change or delete tool
classes (`/toolClasses`). Mappings are merged with those of the base config,
but `group_mapping` has no entries there, so an overlay that sets it lists
the admin groups, too.

### Group membership changes

Group memberships are those of the token: if the group claim is in the access
token, users removed from a group keep its roles, also the role `admin`, until
the token expires. If it is read from the user info
(`security.auth.userinfo_claims`), FOCA caches the user info per token for up
to `security.auth.cache_ttl` seconds (default: 300, but not beyond the
token's expiry; per worker process). So users removed from a group keep its
roles for up to 5 minutes, and users added to a group get them only after
that time (or with a new token). To shorten the delay, lower `cache_ttl`
(which also sets how long the issuers' discovery documents and keys are
cached), or set `security.auth.validate_userinfo: true`, which fetches the
user info for every request with a token (and so also rejects revoked
tokens), at the cost of a request to the identity provider each time (see
FOCA's [authentication](https://foca.readthedocs.io/en/latest/authentication/)).

## Requiring login for reads

Deployments can require login for all reads of TRS, except `GET
/service-info`, with a config overlay, using FOCA's [spec
patches](https://foca.readthedocs.io/en/latest/configuration/api/#patching-specifications)
and [named
entries](https://foca.readthedocs.io/en/latest/configuration/#named-entries).
The app ships a patch for this,
[`trs_filer/api/patches/login-for-reads.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/patches/login-for-reads.yaml),
which sets the security requirements of the public read operations to a
bearer token (`BEARER`, the security scheme of TRS):

```yaml
--8<-- "trs_filer/api/patches/login-for-reads.yaml"
```

Apply it to the API specification (named `trs` in the base config) in an
overlay (the path is relative to the directory of the base config, where the
patch is installed):

```yaml title="overlay.yaml"
api:
    specs:
        trs:
            patches:
                - api/patches/login-for-reads.yaml
```

With the Helm chart, put the same in the `trs_filer.config` value. Requests
to the patched reads without a valid token are then rejected with `401
Unauthorized`; any authenticated user may read, by the default policies (in
`security.access_control.policies`, which are only evaluated for reads that
require login): `list-tools` (`GET /tools`), `get-tools` (`GET` of a tool,
its versions and their descriptors, tests, files and containerfiles, i.e.,
of all paths under `/tools/`) and `list-tool-classes` (`GET /toolClasses`).
`GET /service-info`, the API specification (`openapi.json`) and the Swagger
UI (`ui/`) stay public. The rules allow `HEAD` too, which Flask serves
from the `GET` operations and which access control checks as `HEAD`.

To allow reads for some users only, replace these rules by name in the
overlay, e.g., with rules for a role that a group is mapped to, in addition
to the deployment's admin groups (`null` removes a rule):

```yaml title="readers.yaml"
security:
    access_control:
        group_mapping:
            trs-admins: admin
            trs-readers: reader
        policies:
            list-tools: [p, reader, /ga4gh/trs/v2/tools, "GET|HEAD"]
            get-tools: [p, reader, "/ga4gh/trs/v2/tools/*", "GET|HEAD"]
            list-tool-classes: [p, reader, /ga4gh/trs/v2/toolClasses, "GET|HEAD"]
```

If an overlay of the deployment gives the policies as a list, which replaces
the rules of the base config, add these rules to the list (FOCA refuses named
rules after a list).

!!! danger "With great power comes great responsibility"
    Patches and rules in overlays can weaken or remove authentication and
    access control as easily as they add them. Review them like code, keep
    them as small as possible, and check the startup logs, which list the
    applied patches and warn of operations that patches make public (see
    FOCA's [patching
    specifications](https://foca.readthedocs.io/en/latest/configuration/api/#patching-specifications)).

## Network access

Authentication applies to every request that reaches the app, also from
inside the cluster. Still, with the default values of the Helm chart
(`trs_filer.networkPolicy.enabled: false`), every pod in the cluster can call
the app's Service (`<appName>`, port 8080) directly, set `X-Forwarded-*`
headers, which change the scheme of the links in responses (and, via the
`SCRIPT_NAME` header, their path; `trs_filer.forwardedAllowIps: "*"`), and
set the `Host` header, which changes their host. To let only the ingress
controller or router connect, enable `trs_filer.networkPolicy` with their
pods or namespace in `trs_filer.networkPolicy.ingressFrom`, in a cluster
whose network plugin enforces NetworkPolicies, and narrow
`trs_filer.forwardedAllowIps` (see [Security
notes](deployment.md#security-notes) and [Network
policies](deployment.md#network-policies)).

FOCA's permissions API (`/admin/access-control/`, for admins only, see
[Permissions API](operations.md#permissions-api)) is served like the TRS
API; to keep it off the internet, route only `/ga4gh/trs/v2/` through the
ingress controller, the router or a proxy in front of them.
