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

See your proxy's documentation for how to restrict methods and clients. The
Helm chart's Ingress is off by default; enable it together with
annotations for the ingress controller that restrict writes (see
[Ingress](deployment.md#ingress), with an example for ingress-nginx). On
OpenShift, the chart creates a Route instead, which applies no
restrictions.

Access tokens for writes and ownership of tools are planned (see the [issue
tracker](https://github.com/elixir-cloud-aai/trs-filer/issues)); this page
will describe them.
