# Access control

Tools, their versions and files, and tool classes can be read by anyone,
unless the deployment [requires login for
reads](#requiring-login-for-reads). Writing, i.e., registering, changing and
deleting tools, versions and tool classes (see [Registering
tools](api.md#registering-tools)), requires an access token of an OpenID
Connect provider that the deployment trusts (see
[Authentication](#authentication)). Any authenticated user can register
tools and add tool classes; tools are changed by their owners and
maintainers (see [Roles on tools](#roles-on-tools)), tool classes by admins
(see [Admins](#admins)). The identity provider, its claims and the groups
mapped to roles are deployment configuration, without defaults (see
[Deployment configuration](configuration.md#deployment-configuration)).
Authentication
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
reads](#requiring-login-for-reads)). The TRS reads also accept a token, so
that admins and the users with a role on a pending tool see it (mode
`moderated`, see [Adding tool
classes](configuration.md#adding-tool-classes)); invalid tokens are read as
anonymous.
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
role](#admins) and [roles of groups](#roles-of-groups)). Claims in `security.auth.userinfo_claims` are read from the
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

## Roles on tools

As for services in [Cloud
Registry](https://cloud-registry.readthedocs.io/en/latest/access-control/#roles-on-services):

- Any authenticated user can register a tool (`POST /tools`, or `PUT
  /tools/{id}` with the identifier of no tool) and becomes its **owner**.
  Identifiers of new tools must not contain commas or line breaks (`400 Bad
  Request`), as roles can't be stored for them.
- Owners can replace (`PUT`) and delete (`DELETE`) their tools, add, replace
  and delete their versions, and grant other users the roles `owner` or
  `maintainer` on them, by their user identifier (`sub` claim; with several
  trusted token issuers, namespaced by issuer, as `<namespace>|<sub>`:
  encode it in URLs, slashes may also be kept):

  ```bash
  curl -X PUT "http://localhost:8080/ga4gh/trs/v2/tools/<id>/permissions/users/<user-id>" \
    -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
    -d '{"role": "maintainer"}'
  ```

  `GET /tools/<id>/permissions` lists the roles granted on a tool, as
  `{"subject_type": "user", "subject": <user-id>, "role": <role>}` (and
  `"subject_type": "group"` for [groups](#roles-of-groups)), and `DELETE
  /tools/<id>/permissions/users/<user-id>` revokes them. The last owner of a
  tool can't be removed or downgraded (`409 Conflict`); delete the tool
  instead.
- **Maintainers** can add (`POST /tools/<id>/versions`) and replace (`PUT
  /tools/<id>/versions/<version-id>`) versions, but not delete versions,
  replace or delete the tool, or change its roles.
- [Admins](#admins) can do everything.
- Everybody else gets `403 Forbidden` for changes of tools (`PUT` of a stored
  tool included) and their roles, and for listing the roles.

Deleting a tool revokes all roles granted on it, so a tool registered later
with the same identifier belongs to whoever registers it. Who registered a
tool and when, and when it or one of its versions last changed, is stored
with the tool (internal fields `_createdBy`, `_createdAt` and `_updatedAt`,
not served by the API); replacing a tool keeps who registered it and when.
So is whether the tool is pending, as its tool class is (`_pending`, mode
`moderated`): pending tools are served only to admins and the users with a
role on them.

Tools stored before tools had owners have none: only admins can change
them, and grant them an owner (`PUT /tools/<id>/permissions/users/<user-id>`
with `{"role": "owner"}`); the role `maintainer` is only granted on tools with
an owner (`400 Bad Request` otherwise). See the [upgrade guide](upgrading.md).

Roles are granted, revoked and listed with FOCA's [resource ownership
helpers](https://foca.readthedocs.io/en/latest/access-control/#resource-ownership)
and its ready-made role controllers, for the roles in
`security.access_control.resource_roles` (`owner` and `maintainer`; don't
change them, as the API and the policies are written for them). What each
role may do is set by the named rules of `security.access_control.policies`
(e.g., `owners-change-tools`, `maintainers-add-versions`), which overlays can
change by name. Groups must not be mapped to these roles
(`security.access_control.group_mapping`), as all members of such a group
would have the role on all tools; FOCA refuses to start then.

## Roles of groups

Owners can also grant these roles to **groups** they are members of, by the
group (a value of the group claim, e.g., a group of the team that maintains
the tool), URL-encoded in the path (e.g., `:` as `%3A` and `#` as `%23` for
entitlements); all members of the group then have the role, so team changes
are handled centrally in the identity provider instead of per tool:

```bash
curl -X PUT "http://localhost:8080/ga4gh/trs/v2/tools/<id>/permissions/groups/urn%3Aexample%3Agroup%3Atool-team%23login.example.org" \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"role": "owner"}'
```

Granting roles to groups the owner is not a member of is refused (`403
Forbidden`), as owners could otherwise hand a tool to any group; admins can
grant roles to any group. Any owner can revoke the roles of a group (`DELETE
/tools/<id>/permissions/groups/<group>`). Groups count as owners: the last
user owner can be removed while a group is owner, and the last owner group
can't be removed or downgraded (`409 Conflict`). Roles of groups apply because
the base config sets `security.access_control.keep_group_subjects` (all
values of the group claim are used as subjects, besides the admin group
mapping); don't unset it in overlays.

!!! warning
    All members of an owner group are owners: they can list the identifiers
    of all users with roles on the tool, and remove the other owners, users
    and groups. Don't grant roles to broad groups, e.g., to all members of a
    virtual organization (VO), but to groups of the team that maintains the
    tool.

## Admins

Members of the groups that the deployment maps to the role `admin`
(`security.access_control.group_mapping`) are **admins**: they can do
everything, i.e., register, change and delete all tools, versions and tool
classes, and manage the roles on all tools: tool registries are public, so
their operators must be able to moderate them. E.g., with the group claim
`groups`:

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
change tools of others or tool classes. On startup, FOCA logs the groups
mapped to `admin`.

Tool classes are a vocabulary that all tools share: any authenticated user
can add tool classes (explicitly, or by registering a tool with a new one),
unless the deployment lets only admins add them (mode `controlled`) or
moderates them (mode `moderated`: those of other users are pending until
an admin approves them, `PUT /toolClasses/{id}/approval`; see [Adding tool
classes](configuration.md#adding-tool-classes)). Only admins can replace
(`PUT` of a stored tool class), approve and delete them, as no policy
allows it to other users. Unlike
Cloud Registry, TRS-Filer has no admin mode yet: admins act as admins on
every request, without the header `X-Request-Roles`.

To let other users change all tools, map a group to a role of your own and
give the role write rules in a config overlay, e.g., for editors who may
replace and delete all tools and versions:

```yaml title="editors.yaml"
security:
    access_control:
        group_mapping:
            trs-admins: admin
            trs-editors: editor
        policies:
            editors-change-tools: [p, editor, "/ga4gh/trs/v2/tools/:id", "(PUT)|(DELETE)"]
            editors-add-versions: [p, editor, "/ga4gh/trs/v2/tools/:id/versions", POST]
            editors-change-versions: [p, editor, "/ga4gh/trs/v2/tools/:id/versions/:version_id", "(PUT)|(DELETE)"]
```

Editors can then change all tools, also those that others registered, but
not their roles, nor replace or delete tool classes (`/toolClasses`). Don't
give such roles rules for all paths under `/tools/` (e.g.,
`/ga4gh/trs/v2/tools/*`), as these would also let them change the roles on
tools (`/tools/{id}/permissions/...`), i.e., make themselves owners.
Mappings are merged with those of the base config,
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

With the Helm chart, put the same in the `config` value. Requests
to the patched reads without a valid token are then rejected with `401
Unauthorized`; any authenticated user may read, by the default policies (in
`security.access_control.policies`, which are only evaluated for reads that
require login): `list-tools` (`GET /tools`), `get-tools` (`GET` of a tool),
`list-versions` (`GET` of its versions), `get-versions` (`GET` of a version
and its descriptors, tests, files and containerfiles, i.e., of all paths
under `/tools/{id}/versions/`) and `list-tool-classes` (`GET /toolClasses`).
The roles on tools (`GET /tools/{id}/permissions`) always need a token, of an
owner of the tool or an admin.
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
            get-tools: [p, reader, "/ga4gh/trs/v2/tools/:id", "GET|HEAD"]
            list-versions: [p, reader, "/ga4gh/trs/v2/tools/:id/versions", "GET|HEAD"]
            get-versions: [p, reader, "/ga4gh/trs/v2/tools/:id/versions/*", "GET|HEAD"]
            list-tool-classes: [p, reader, /ga4gh/trs/v2/toolClasses, "GET|HEAD"]
```

If an overlay of the deployment gives the policies as a list, which replaces
the rules of the base config, add these rules to the list (FOCA refuses named
rules after a list). Don't give readers rules for all paths under `/tools/`
(e.g., `/ga4gh/trs/v2/tools/*`), as these would also let them list the roles
on tools (`/tools/{id}/permissions`).

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
(`trsFiler.networkPolicy.enabled: false`), every pod in the cluster can call
the app's Service (`<app>`, port 8080) directly and set the `Host` header,
which changes the host of the links in responses; if `FORWARDED_ALLOW_IPS`
trusts their addresses, also `X-Forwarded-*` headers, which change their
scheme (and, via the `SCRIPT_NAME` header, their path). To let only the
ingress controller or router connect, enable `trsFiler.networkPolicy` with
their pods or namespace in `trsFiler.networkPolicy.ingressFrom`, in a
cluster whose network plugin enforces NetworkPolicies, and trust forwarded
headers only from them (see [Forwarded
headers](deployment.md#forwarded-headers) and [Network
policies](deployment.md#network-policies)).

FOCA's permissions API (`/admin/access-control/`, for admins only, see
[Permissions API](operations.md#permissions-api)) is served like the TRS
API; to keep it off the internet, route only `/ga4gh/trs/v2/` through the
ingress controller, the router or a proxy in front of them.
