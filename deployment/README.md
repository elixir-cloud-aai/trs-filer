# TRS filer Helm chart

## Quick start

1. Edit `values.yaml`. It is important to change `host_name` to the URL you want the application to respond to.

2. Install the Helm chart. Run this from the `deployment` folder:
```
helm install trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster should be installed.
`trs-filer` could be any name, it will be referenced later for upgrading or uninstalling.

## Upgrades

If you need to change any parameter of the deployment, the procedure is similar to installing:

1. Edit `values.yaml` with the new configuration you want to apply. For example, if you want to change the image of trs-filer, change `trs_filer.image`.

2. Upgrade the Helm chart. Run this from the `deployment` folder:
```
helm upgrade trs-filer . -n namespace
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
of an existing database (with `mongo`, the old shell, instead of
`mongosh` for images before 6.0, e.g., 3.6):

```bash
kubectl exec deploy/mongodb-trs-filer -n namespace -- mongosh --quiet --eval \
  'printjson({version: db.version(), fcv: db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion})'
```

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

### Persistence

MongoDB keeps its data in the PersistentVolumeClaim `mongodb-<appName>` (by
default `mongodb-trs-filer`, of `mongodb.volumeSize`). The claim is
annotated with `helm.sh/resource-policy: keep`, so Helm keeps it, and the
database, when the release is uninstalled; installing a release with the
same name and `trs_filer.appName` in the same namespace uses it again (Helm
refuses to install a release of another name over it). Delete it by hand to
remove the data (`kubectl delete pvc mongodb-trs-filer -n namespace`).
