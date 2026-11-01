# TRS filer Helm chart

> **Warning:** TRS-Filer has no authentication yet: anyone who can reach the
> API can register, replace and delete tools and tool classes. Allow `POST`,
> `PUT` and `DELETE` only from trusted clients, at the ingress controller (see
> [Ingress](#ingress)) or at a proxy in front of the cluster (see
> [Access control](https://trs-filer.readthedocs.io/en/latest/access-control/)).
> The chart restricts nothing by default.

## Quick start

1. Edit `values.yaml`. It is important to change `host_name` to the URL you want the application to respond to.

2. Install the Helm chart. Run this from the `deployment` folder:
```
helm install trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster should be installed.
`trs-filer` could be any name, it will be referenced later for upgrading or uninstalling.

## Ingress

The chart exposes the app for `host_name` via an Ingress
(`trs_filer.ingress.enabled`, by default `true`) or, if it is disabled and
the cluster serves Routes, an OpenShift Route (with TLS at the router). The
Ingress routes all paths (`/`) to the app and is configured with:

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

## Upgrades

If you need to change any parameter of the deployment, the procedure is similar to installing:

1. Edit `values.yaml` with the new configuration you want to apply. For example, if you want to change the image of trs-filer, change `trs_filer.image`.

2. Upgrade the Helm chart. Run this from the `deployment` folder:
```
helm upgrade trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster was installed.
`trs-filer` is the name given when installing. In order to see the correct name, do a `helm ls -n namespace`.
