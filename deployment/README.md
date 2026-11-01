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
defaults (one worker with four threads), the app uses about 90 MB at rest
(worker and master) and peaked at about 175 MB in a test with 12 concurrent
registrations of about 1 MB each plus downloads and listings; the request
covers that, and the limit leaves room for larger responses. Each further
Gunicorn worker (`GUNICORN_CMD_ARGS`, see
[Server](https://trs-filer.readthedocs.io/en/latest/configuration/#server))
loads the whole app, so add about 150Mi per worker to the request and the
limit. `mongodb.resources` sets those of MongoDB (by default 512Mi).

## Upgrades

If you need to change any parameter of the deployment, the procedure is similar to installing:

1. Edit `values.yaml` with the new configuration you want to apply. For example, if you want to change the image of trs-filer, change `trs_filer.image`.

2. Upgrade the Helm chart. Run this from the `deployment` folder:
```
helm upgrade trs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster was installed.
`trs-filer` is the name given when installing. In order to see the correct name, do a `helm ls -n namespace`.
