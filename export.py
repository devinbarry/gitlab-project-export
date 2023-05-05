import os
import re
import sys
import time
import argparse
from datetime import datetime
import requests
from gitlab_export import config
from gitlab_export.gitlab import Api

return_code = 0
debug = False

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="""
        GitLab Project Export is a
        small project using GitLab API for exporting whole gitlab
        project with wikis, issues etc.
        Good for migration or simple backup of your gitlab projects.
        """,
        epilog='Created by Robert Vojcik <robert@vojcik.net>')

    # Arguments
    parser.add_argument(
        '-c', dest='config', default='config.yaml',
        help='config file'
    )
    parser.add_argument(
        '-d', dest='debug', default=False, action='store_const',
        const=True, help='Debug mode'
    )
    parser.add_argument(
        '-f', dest='force', default=False, action='store_const',
        const=True, help='Force mode - overwrite backup file if exists'
    )
    parser.add_argument(
        '-n', dest='noop', default=False, action='store_const',
        const=True, help='Only print what would be done, without doing it'
    )

    return parser.parse_args()


def prepare_config_variables(c):
    token = c.config["gitlab"]["access"]["token"]
    gitlab_url = c.config["gitlab"]["access"]["gitlab_url"]
    ssl_verify = c.config["gitlab"]["access"]["ssl_verify"]
    wait_between_exports = c.config['gitlab'].get('wait_between_exports', 0)
    membership = c.config['gitlab'].get('membership', True)
    include_archived = c.config['gitlab'].get('include_archived', False)
    max_tries_number = c.config['gitlab'].get('max_tries_number', 12)
    retention_period = c.config['backup'].get('retention_period', 0)
    exclude_projects = c.config["gitlab"].get('exclude_projects', [])

    if not (isinstance(retention_period, (int, float)) and retention_period >= 0):
        print("Invalid value for retention_period. ignoring")
        retention_period = 0

    return (token, gitlab_url, ssl_verify, wait_between_exports, membership, include_archived, max_tries_number,
            retention_period, exclude_projects)


def init_gitlab_api(gitlab_url, token, ssl_verify):
    if debug:
        print(f"{gitlab_url}, token")
    return Api(gitlab_url, token, ssl_verify)


def get_projects_to_export(gitlab, c, membership, include_archived, exclude_projects):
    export_projects = []
    projects = gitlab.project_list(membership=str(membership), archived=str(include_archived))
    if not projects:
        print("Unable to get projects for your account", file=sys.stderr)
        sys.exit(1)

    # Create export_projects array
    for project_pattern in c.config["gitlab"]["projects"]:
        for gitlab_project in projects:
            if re.match(project_pattern, gitlab_project):
                export_projects.append(gitlab_project)

    # Remove any projects that are marked as excluded
    for ignored_project_pattern in exclude_projects:
        for gitlab_project in projects:
            if re.match(ignored_project_pattern, gitlab_project):
                if debug:
                    print(f"Removing project '{gitlab_project}' from export (exclusion: '{ignored_project_pattern}'): ")
                export_projects.remove(gitlab_project)

    return export_projects

def create_project_directory(c, project):
    destination = c.config["backup"]["destination"]
    if c.config["backup"]["project_dirs"]:
        destination += f"/{project}"

    try:
        os.makedirs(destination, exist_ok=True)
    except OSError as e:
        print(f"Unable to create directories {destination}: {e}", file=sys.stderr)
        sys.exit(1)

    return destination

def prepare_destination_file(c, project, destination):
    d = datetime.now()
    file_tmpl = c.config["backup"]["backup_name"]
    dest_file = destination + "/" + file_tmpl.replace("{PROJECT_NAME}", project.replace("/", "-"))
    dest_file = dest_file.replace("{TIME}", d.strftime(c.config["backup"]["backup_time_format"].replace(" ", "_")))

    return dest_file

def export_project(args, gitlab, project, destination, dest_file, max_tries_number, ssl_verify, token,
                   retention_period, wait_between_exports, export_projects):
    global return_code

    if debug:
        print(f" Destination {destination}")

    if os.path.isfile(dest_file):
        if not args.force:
            print(f"File {dest_file} already exists", file=sys.stderr)
            return_code += 1
            return
        else:
            print(f"File {dest_file} already exists - will be overwritten")
            os.remove(dest_file)

    if retention_period > 0:
        purge_old_files(destination, retention_period)

    status = gitlab.project_export(project, max_tries_number)

    if status:
        download_exported_project(gitlab, project, dest_file, ssl_verify, token)
    else:
        print(f"Export failed for project {project}", file=sys.stderr)
        return_code += 1

    if project != export_projects[-1]:
        if debug:
            print(f"Waiting between exports for {wait_between_exports} seconds")
        time.sleep(wait_between_exports)

def purge_old_files(destination, retention_period):
    if debug:
        print(f" Purging files older than {retention_period:.2f} days in the folder {destination}")

    now = time.time()
    for f in os.listdir(destination):
        if not f.endswith(".tar.gz"):
            continue

        f = os.path.join(destination, f)
        if os.path.isfile(f):
            if os.stat(f).st_mtime < now - (retention_period * 86400):
                if debug:
                    print(f"   deleting backup {f}")
                os.remove(f)

def download_exported_project(gitlab, project, dest_file, ssl_verify, token):
    global return_code
    if debug:
        print(f"Success for {project}")

    url = gitlab.download_url["api_url"]
    if debug:
        print(f" URL: {url}")

    r = requests.get(url, allow_redirects=True, stream=True, verify=ssl_verify, headers={"PRIVATE-TOKEN": token})

    if r.status_code >= 200 and r.status_code < 300:
        with open(dest_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
    else:
        print(f"Unable to download project {project}. Got code {r.status_code}: {r.text}", file=sys.stderr)
        return_code += 1


def main():
    global return_code
    global debug

    args = parse_arguments()
    debug = args.debug

    if not os.path.isfile(args.config):
        print(f"Unable to find config file {args.config}")
        sys.exit(1)

    c = config.Config(args.config)

    token, gitlab_url, ssl_verify, wait_between_exports, membership, include_archived, max_tries_number, retention_period, exclude_projects = prepare_config_variables(c)
    gitlab = init_gitlab_api(gitlab_url, token, ssl_verify)
    export_projects = get_projects_to_export(gitlab, c, membership, include_archived, exclude_projects)

    if debug:
        print(f"Projects to export: {export_projects}")

    if args.noop:
        print("Not running actual export because of -n/--noop flag.")
        sys.exit(0)

    for project in export_projects:
        if debug:
            print(f"Exporting {project}")

        destination = create_project_directory(c, project)
        dest_file = prepare_destination_file(c, project, destination)

        if debug:
            print(f" Destination file {dest_file}")

        export_project(args, gitlab, project, destination, dest_file, max_tries_number, ssl_verify, token, retention_period, wait_between_exports, export_projects)

    sys.exit(return_code)


if __name__ == '__main__':
    main()
