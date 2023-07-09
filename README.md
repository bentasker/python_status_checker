# Python HTTP Status Checker

A Prefect flow designed to run HTTP/1 and HTTP/2 reachability checks against monitored URLs.

Probe metrics are then written into InfluxDB for later consumption, ultimately, feeding in to [My Status Page](https://bentasker.github.io/status_page/)


----

### Linking local runs to Prefect Cloud

- Login at [https://app.prefect.cloud/](https://app.prefect.cloud/)
- [Create a workspace](https://docs.prefect.io/2.10.18/cloud/cloud-quickstart/#create-a-workspace)
- Create an API key at [https://app.prefect.cloud/my/api-keys](https://app.prefect.cloud/my/api-keys)
- Install Prefect locally (`pip install prefect`)

Login:
```sh
prefect cloud login
```

Choose paste an API key and provide the key.

Running the script
```sh 
./status-checks.py 
```

Should lead to logs being available in the Cloud UI

----

### Github Workflow config

Aquire an InfluxDB token with write privileges on the relevant InfluxDB bucket


In Github:

- Go to the relevant repo
- Choose `Settings`
- Choose `Secrets and variables`
- Choose `Actions`
- Click `New repository secret`
- Name the secret `INFLUXDB_TOKEN`
- Set the value to your token
- Create another called `INFLUXDB_URL` with the URL to your instance
- A third called `INFLUXDB_BUCKET` with the name of your destination bucket

It's also necessary to populate secrets detailing how to communicate with your Prefect cloud account

- Create a secret called `PREFECT_API_KEY` and provide your Prefect API Key
- Create another called `PREFECT_WORKSPACE` with the name of your workspace (which is `accountname/workspacename`)

----

### Copyright

Copyright 2023, B Tasker. Released under [BSD 3 Clause](https://www.bentasker.co.uk/pages/licenses/bsd-3-clause.html).
