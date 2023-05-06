import os
import re
import sys
import time
import argparse
from datetime import datetime
import requests
from gitlab_export import config
from gitlab_export.client import GitlabClient

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
    max_tries_number = c.config['gitlab'].get('max_tries_number', 12)
    retention_period = c.config['backup'].get('retention_period', 0)

    if not (isinstance(retention_period, (int, float)) and retention_period >= 0):
        print("Invalid value for retention_period. ignoring")
        retention_period = 0

    return token, gitlab_url, ssl_verify, wait_between_exports, retention_period


def get_projects_to_export(gitlab_client, c):
    membership = c.config['gitlab'].get('membership', True)
    archived = c.config['gitlab'].get('include_archived', False)
    exclude_projects = c.config["gitlab"].get('exclude_projects', [])

    export_projects = []
    all_projects = gitlab_client.list_all_projects(membership=str(membership), archived=str(archived))
    if not all_projects:
        print("Unable to get projects for your account", file=sys.stderr)
        sys.exit(1)

    # Select all projects that match the project pattern
    for project_pattern in c.config["gitlab"]["projects"]:
        for gitlab_project in all_projects.keys():
            if re.match(project_pattern, gitlab_project):
                export_projects.append(gitlab_project)

    # Remove any projects that are marked as excluded
    for ignored_project_pattern in exclude_projects:
        for gitlab_project in all_projects.keys():
            if re.match(ignored_project_pattern, gitlab_project):
                if debug:
                    print(f"Removing project '{gitlab_project}' from export (exclusion: '{ignored_project_pattern}'): ")
                export_projects.remove(gitlab_project)

    # Create a map of project names to project IDs as the final response
    output = {}
    for project in export_projects:
        output[project] = all_projects[project]
    return output

def create_project_directory(c, project_name):
    project_dir = c.config["backup"]["destination"]
    if c.config["backup"]["project_dirs"]:
        project_dir += f"/{project_name}"

    try:
        os.makedirs(project_dir, exist_ok=True)
    except OSError as e:
        print(f"Unable to create directories {project_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    return project_dir

def _create_file_name(c, project_name, project_dir):
    d = datetime.now()
    file_tmpl = c.config["backup"]["backup_name"]
    dest_file = project_dir + "/" + file_tmpl.replace("{PROJECT_NAME}", project_name.replace("/", "-"))
    dest_file = dest_file.replace("{TIME}", d.strftime(c.config["backup"]["backup_time_format"].replace(" ", "_")))

    return dest_file

def export_project(client, project_id, project_name, dest_file, ssl_verify, token, download_only=False):
    global return_code

    if download_only:
        download_url = client.get_download_link(project_id=project_id)
    else:
        download_url = client.export_project(project_id=project_id)

    if download_url is not None:
        if debug:
            print(f'Download URL: {download_url}')
        return_code += download_exported_project(download_url, project_name, dest_file, ssl_verify, token)
    else:
        print(f"Export failed for project {project_name}", file=sys.stderr)
        return_code += 1


def setup_download_directory(project_dir, dest_file, retention_period, args):
    """
    Set up a download directory by ensuring the destination file is ready for download and purging old files.

    :param project_dir: The directory where the project is located.
    :param dest_file: The file to be prepared for download.
    :param retention_period: The number of days for which files should be retained in the project directory.
    :param args: A collection of command-line arguments, including a 'force' option to overwrite existing files.
    """
    global return_code

    if debug:
        print(f"Destination {project_dir}")

    if os.path.isfile(dest_file):
        if not args.force:
            print(f"File {dest_file} already exists", file=sys.stderr)
            return_code += 1
            return
        else:
            print(f"File {dest_file} already exists - will be overwritten")
            os.remove(dest_file)

    if retention_period > 0:
        purge_old_files(project_dir, retention_period)



def purge_old_files(project_dir, retention_period):
    if debug:
        print(f" Purging files older than {retention_period:.2f} days in the folder {project_dir}")

    now = time.time()
    for f in os.listdir(project_dir):
        if not f.endswith(".tar.gz"):
            continue

        f = os.path.join(project_dir, f)
        if os.path.isfile(f):
            if os.stat(f).st_mtime < now - (retention_period * 86400):
                if debug:
                    print(f"Deleting backup {f}")
                os.remove(f)

def download_exported_project(download_url, project, dest_file, ssl_verify, token):
    """
    function returns either 0 (success) or 1 (failure).
    """
    r = requests.get(download_url, allow_redirects=True, stream=True, verify=ssl_verify,
                     headers={"PRIVATE-TOKEN": token})

    if 200 <= r.status_code < 300:
        with open(dest_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        return 0
    else:
        print(f"Unable to download project {project}. Got code {r.status_code}: {r.text}", file=sys.stderr)
        return 1



def main():
    global return_code
    global debug

    args = parse_arguments()
    debug = args.debug

    if not os.path.isfile(args.config):
        print(f"Unable to find config file {args.config}")
        sys.exit(1)

    c = config.Config(args.config)

    token, gitlab_url, ssl_verify, wait_between_exports, retention_period = prepare_config_variables(c)

    if debug:
        print(f"Initialising GitlabClient with URL: {gitlab_url}")
    client = GitlabClient(gitlab_url, token, ssl_verify)

    export_projects = get_projects_to_export(gitlab_client=client, c=c)
    if debug:
        print(f"Projects to export: {export_projects}")

    if args.noop:
        print("Not running actual export because of -n/--noop flag.")
        sys.exit(0)

    for project_name, project_id in export_projects.items():
        if debug:
            print(f"Exporting {project_name} - {project_id}")

        project_dir = create_project_directory(c, project_name)
        dest_file = _create_file_name(c, project_name, project_dir)

        if debug:
            print(f" Destination file {dest_file}")

        setup_download_directory(project_dir, dest_file, retention_period, args)
        export_project(client, project_id, project_name, dest_file, ssl_verify, token)

        if debug:
            print(f"Waiting between exports for {wait_between_exports} seconds")
        time.sleep(wait_between_exports)

    sys.exit(return_code)


if __name__ == '__main__':
    main()
