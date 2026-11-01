# TRS filer Helm chart

## Quick start

1. Edit `values.yaml`. It is important to change `host_name` to the URL you want the application to respond to.

2. Install the Helm chart. Run this from the `deployment` folder:
```
helm install trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster should be installed.
`trs-filer` could be any name, it will be referenced later for upgrading or uninstalling.

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
