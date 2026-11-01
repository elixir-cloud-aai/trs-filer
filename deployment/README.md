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
(`https://<host_name>:443`) and the MongoDB host and database: a Job
(`configmap-job-<appName>-<revision>`, run on every install and upgrade)
renders these into the base config of the image and writes the result to
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
   changing the overlay (`kubectl rollout restart deploy/trs-filer -n
   namespace`).

## Upgrades

If you need to change any parameter of the deployment, the procedure is similar to installing:

1. Edit `values.yaml` with the new configuration you want to apply. For example, if you want to change the image of trs-filer, change `trs_filer.image`.

2. Upgrade the Helm chart. Run this from the `deployment` folder:
```
helm upgrade trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster was installed.
`trs-filer` is the name given when installing. In order to see the correct name, do a `helm ls -n namespace`.
