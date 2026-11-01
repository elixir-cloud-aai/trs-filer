# TRS filer Helm chart

## Quick start

1. Edit `values.yaml`. It is important to change `host_name` to the URL you want the application to respond to.

2. Install the Helm chart. Run this from the `deployment` folder:
```
helm install trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster should be installed.
`trs-filer` could be any name, it will be referenced later for upgrading or uninstalling.

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
