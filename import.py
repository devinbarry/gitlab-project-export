import sys
import os
import argparse
from gitlab_export import config, gitlab


return_code = 0

if __name__ == '__main__':
    # Parsing arguments
    parser = argparse.ArgumentParser(
        description="""
        GitLab Project Import is
        small project using Gitlab API for exporting whole gitlab
        project with wikis, issues etc.
        Good for migration or simple backup your gitlab projects.
        """,
        epilog='Created by Robert Vojcik <robert@vojcik.net>')

    # Arguments
    parser.add_argument(
        '-c', dest='config', default='config.yaml',
        help='config file')
    parser.add_argument(
        '-f', dest='filepath', default=False,
        help='Path to gitlab exported project file')
    parser.add_argument(
        '-p', dest='project_path', default=False,
        help='Project path')
    parser.add_argument(
        '-d', dest='debug', default=False, action='store_const', const=True,
        help='Debug mode')

    args = parser.parse_args()

    if not os.path.isfile(args.config):
        print(f"Unable to find config file {args.config}")

    c = config.Config(args.config)
    token = c.config["gitlab"]["access"]["token"]
    gitlab_url = c.config["gitlab"]["access"]["gitlab_url"]
    ssl_verify = c.config["gitlab"]["access"]["ssl_verify"]

    # Init gitlab api object
    if args.debug:
        print(f"{gitlab_url}, token")
    gitlab = gitlab.Api(gitlab_url, token, ssl_verify)

    # import project
    if args.project_path and args.filepath and os.path.isfile(args.filepath):
        if args.debug:
            print(f"Importing {args.project_path}")
        status = gitlab.project_import(args.project_path, args.filepath)

        # Import successful
        if status:
            print(f"Import success for {args.project_path}")
            sys.exit(0)
        else:
            print("Import was not successful")
            sys.exit(1)

    else:
        print("Error, you have to specify correct project_path and filepath")
        sys.exit(1)
