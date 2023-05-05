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

def main():
    global return_code

    # Parsing arguments
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

    args = parser.parse_args()

    if not os.path.isfile(args.config):
        print(f"Unable to find config file {args.config}")

    c = config.Config(args.config)
    token = c.config["gitlab"]["access"]["token"]
    gitlab_url = c.config["gitlab"]["access"]["gitlab_url"]
    ssl_verify = c.config["gitlab"]["access"]["ssl_verify"]

    # Check additional config
    wait_between_exports = c.config['gitlab'].get('wait_between_exports', 0)
    membership = c.config['gitlab'].get('membership', True)
    include_archived = c.config['gitlab'].get('include_archived', False)
    max_tries_number = c.config['gitlab'].get('max_tries_number', 12)
    retention_period = c.config['backup'].get('retention_period', 0)
    exclude_projects = c.config["gitlab"].get('exclude_projects', [])
    if not (isinstance(retention_period, (int, float)) and retention_period >= 0):
        print("Invalid value for retention_period. ignoring")
        retention_period = 0

    # Init gitlab api object
    if args.debug:
        print(f"{gitlab_url}, token")

    gitlab = Api(gitlab_url, token, ssl_verify)

    # Export each project
    export_projects = []

    # Get All member projects from gitlab
    projects = gitlab.project_list(membership=str(membership), archived=str(include_archived))
    if not projects:
        print("Unable to get projects for your account", file=sys.stderr)
        sys.exit(1)

    # Check projects against config
    # Create export_projects array
    for project_pattern in c.config["gitlab"]["projects"]:
        for gitlabProject in projects:
            if re.match(project_pattern, gitlabProject):
                export_projects.append(gitlabProject)

    # Remove any projects that are marked as excluded
    for ignored_project_pattern in exclude_projects:
        for gitlabProject in projects:
            if re.match(ignored_project_pattern, gitlabProject):
                if args.debug:
                    print(f"Removing project '{gitlabProject}' from export (exclusion: '{ignored_project_pattern}'): ")
                export_projects.remove(gitlabProject)

    if args.debug:
        print(f"Projects to export: {export_projects}")

    if args.noop:
        print("Not running actual export because of -n/--noop flag.")
        sys.exit(0)

    for project in export_projects:
        if args.debug:
            print(f"Exporting {project}")

        # Download project to our destination
        destination = c.config["backup"]["destination"]
        if c.config["backup"]["project_dirs"]:
            destination += f"/{project}"

        # Create directories
        if not os.path.isdir(destination):
            try:
                os.makedirs(destination)
            except Exception:
                print(f"Unable to create directories {destination}", file=sys.stderr)
                sys.exit(1)

        if args.debug:
            print(f" Destination {destination}")

        # Prepare actual date
        d = datetime.now()
        # File template from config
        file_tmpl = c.config["backup"]["backup_name"]
        # Project name in dest_file
        dest_file = destination + "/" + file_tmpl.replace("{PROJECT_NAME}", project.replace("/", "-"))
        # Date in dest_file
        dest_file = dest_file.replace("{TIME}", d.strftime(c.config["backup"]["backup_time_format"].replace(" ", "_")))

        if args.debug:
            print(f" Destination file {dest_file}")

        if os.path.isfile(dest_file):
            if not args.force:
                print(f"File {dest_file} already exists", file=sys.stderr)
                return_code += 1
                continue
            else:
                print(f"File {dest_file} already exists - will be overwritten")
                os.remove(dest_file)

        # Purge old files, if applicable
        if retention_period > 0:
            if args.debug:
                print(f" Purging files older than {retention_period:.2f} days in the folder {destination}")

            now = time.time()
            for f in os.listdir(destination):
                if not f.endswith(".tar.gz"):
                    continue

                f = os.path.join(destination, f)
                if os.path.isfile(f):
                    if os.stat(f).st_mtime < now - (retention_period * 86400):
                        if args.debug:
                            print(f"   deleting backup {f}")
                        os.remove(f)

        # Initiate export
        status = gitlab.project_export(project, max_tries_number)

        # Export successful
        if status:
            if args.debug:
                print(f"Success for {project}")
            # Get URL from gitlab object
            url = gitlab.download_url["api_url"]
            if args.debug:
                print(f" URL: {url}")

            # Download file
            r = requests.get(
                url,
                allow_redirects=True,
                stream=True,
                verify=ssl_verify,
                headers={"PRIVATE-TOKEN": token})

            if r.status_code >= 200 and r.status_code < 300:
                with open(dest_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
            else:
                print(
                    f"Unable to download project {project}. Got code {r.status_code}: {r.text}",
                    file=sys.stderr)
                return_code += 1

        else:
            # Export for project unsuccessful
            print(f"Export failed for project {project}", file=sys.stderr)
            return_code += 1

        # If set, wait between exports
        if project != export_projects[-1]:
            if args.debug:
                print(f"Waiting between exports for {wait_between_exports} seconds")
            time.sleep(wait_between_exports)

    sys.exit(return_code)

if __name__ == '__main__':
    main()
