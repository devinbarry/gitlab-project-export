# gitlab-project-export

Simple Python project for importing/exporting Gitlab projects with [Project import and export](https://docs.gitlab.com/ee/api/project_import_export.html) feature in GitLab API.

Confrms to the V4 API for Gitlab CE, EE and Gitlab.com. Tested against latest Gitlab CE 15.11.2

## Features

- Allows moving projects between Gitlab instances.
- Allows backup of multiple projects in one run.
- Save backups to local directory or remote server via SSH.
- Purge old backups.
- Can be used in cron.

## Changes

### May 2023

Project forked from [Robert Vojcik](https://github.com/rvojcik/gitlab-project-export) to add support for Gitlab CE 15.11.2 and to add a few features.
Code cleaned up and refactored to use modern Python 3.10+ features.

## Prerequisite

* Configured Gitlab API Token: https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html

## Install

Simply install via pip:


`pip install git+https://github.com/devinbarry/gitlab-project-export`

or clone the project and install manually:

```bash
git clone https://github.com/devinbarry/gitlab-project-export
cd gitlab-project-export/
sudo python3 setup.py install
```

or use it without installing to your environment (install only requirements):

```bash
git clone https://github.com/devinbarry/gitlab-project-export
cd gitlab-project-export/
pip install -f requirements.txt
```

## Usage

```bash
usage: export.py [-h] [-c CONFIG] [-d] [-f]

optional arguments:
  -h, --help  show this help message and exit
  -c CONFIG   config file
  -d          Debug mode
  -f          Force mode - overwrite backup file if exists
  -n          Only print what would be done, without doing it
```

```bash
usage: import.py [-h] [-c CONFIG] [-f FILEPATH] [-p PROJECT_PATH] [-d]

optional arguments:
  -h, --help       show this help message and exit
  -c CONFIG        config file
  -f FILEPATH      Path to gitlab exported project file
  -p PROJECT_PATH  Project path
  -d               Debug mode
```

Prepare and edit your config file

`mv config-example.yml config.yml`

Simply run the script with optional config parameter

`python export.py -c /path/to/config.yml`

## Configuration

System uses simple yaml file as configuration.

Example below

```
gitlab:                                                   - gitlab configuration
  access:
    gitlab_url: "https://gitlab.com"                      - GitLab url, official or your instance
    token: "MY_PERSONAL_SECRET_TOKEN"                     - personal access token
  projects:                                               - list of projects to export
    - rvojcik/example-project

backup:                                                   - backup configuration
  destination: "/data/backup"                             - base backup dir
  project_dirs: True                                      - store projects in separate directories
  backup_name: "gitlab-com-{PROJECT_NAME}-{TIME}.tar.gz"  - backup file template
  backup_time_format: "%Y%m%d"                            - TIME template, use whatever compatible with
                                                            python datetime - date.strftime()
  retention_period: 3                                     - purge files in the destination older than the specified value (in days)
  ```

### Backup use-case in cron

Create cron file in `/etc/cron.d/gitlab-backup`

With following content

```bash
MAILTO=your_email@here.tld

0 1 * * * root /path/to/cloned-repo/export.py -c /etc/gitlab-export/config.yml

```

### Migration use-case

First create two config files

`config1.yml` for exporting our project from gitlab.com

```
gitlab:                                                   - gitlab configuration
  access:
    gitlab_url: "https://gitlab.com"                      - GitLab url, official or your instance
    token: "MY_PERSONAL_SECRET_TOKEN"                     - personal access token
  projects:                                               - list of projects to export
    - rvojcik/project1
    - rvojcik/project2

backup:                                                   - backup configuration
  destination: "/data/export-dir"                         - base backup dir
  backup_name: "gitlab-com-{PROJECT_NAME}-{TIME}.tar.gz"  - backup file template
  backup_time_format: "%Y%m%d"                            - TIME template, use whatever compatible with
                                                            python datetime - date.strftime()
```

and `config2.yml` where we need only gitlab access part for importing projects to private gitlab instance

```
gitlab:                                                   - gitlab configuration
  access:
    gitlab_url: "https://gitlab.privatedomain.tld"        - GitLab url, official or your instance
    token: "MY_PERSONAL_SECRET_TOKEN"                     - personal access token
```

Now it's time to export our projects

```bash
python export.py -c ./config1.yml -d
```

Your projects are now exported in `/data/export-dir`

After that we use `import.py` with `config2.yml` for importing into our private gitlab instance.

```bash
./import.py -c ./config2.yml -f ./gitlab-com-rvojcik-project1-20181224.tar.gz -p "rvojcik/project1"
./import.py -c ./config2.yml -f ./gitlab-com-rvojcik-project2-20181224.tar.gz -p "rvojcik/project2"
```

Done ;)
