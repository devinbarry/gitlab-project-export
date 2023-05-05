import requests
import urllib
import sys
import time
import os
import re


class GitlabClient:
    """Api class for gitlab"""

    def __init__(self, gitlab_url, token, ssl_verify=True):
        """Init config object"""
        self.headers = {"PRIVATE-TOKEN": token}
        self.api_url = gitlab_url + "/api/v4"
        self.project_array = False
        self.ssl_verify = ssl_verify

    def _api_request(self, method, endpoint, **kwargs):
        """Generic API request wrapper with error handling"""
        try:
            response = requests.request(method, f"{self.api_url}{endpoint}",
                                        headers=self.headers, verify=self.ssl_verify, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(e, file=sys.stderr)
            sys.exit(1)

    def _api_export(self, project_url):
        """Send export request to API"""
        return self._api_request("POST", f"/projects/{project_url}/export")

    def _api_import(self, project_name, namespace, filename):
        """Send import request to API"""
        data = {
            "path": project_name,
            "namespace": namespace,
            "overwrite": True
        }
        with open(filename, 'rb') as file:
            return self._api_request("POST", "/projects/import", data=data, files={"file": file})

    def _api_status(self, project_url):
        """Check project status"""
        return self._api_request("GET", f"/projects/{project_url}/export")

    def _api_get(self, endpoint, params=None):
        """Get API endpoint data"""
        return self._api_request("GET", endpoint, params=params)

    def _api_post(self, endpoint, data):
        """POST API endpoint data"""
        return self._api_request("POST", endpoint, data=data)

    def _api_import_status(self, project_url):
        """Check project import status"""
        return self._api_request("GET", f"/projects/{project_url}/import")

    def project_list(self, path_glob="", membership="True", archived="False"):
        """List projects based on glob path"""
        params = {
            "simple": "True",
            "membership": membership,
            "archived": archived,
            "per_page": "50"
        }
        page = 1
        output = []
        if not self.project_array:
            while True:
                params["page"] = str(page)
                r = self._api_get('/projects', params=params)
                json = r.json()
                if len(json) > 0:
                    for project_data in json:
                        ppath = project_data["path_with_namespace"]
                        output.append(ppath)
                    page += 1
                else:
                    break
            self.project_array = output

        # Compare glob to projects
        output = []
        for project in self.project_array:
            if re.match(path_glob, project):
                output.append(project)

        return output

    def project_export(self, project_path, max_tries_number):
        """
        Export Gitlab project. When project export is finished, store download URLs
        in objects variable download_url ready to be downloaded.
        """
        url_project_path = urllib.parse.quote(project_path, safe='')

        # Export project
        response = self._api_export(url_project_path)
        if not 200 <= response.status_code < 300:
            print(f"API responded with an unexpected status: {response.status_code} - {response.text}", file=sys.stderr)
            return False

        for _ in range(max_tries_number):
            try:
                response = self._api_status(url_project_path)
            except requests.exceptions.RequestException as e:
                print(e, file=sys.stderr)
                return False

            if response.status_code != requests.codes.ok:
                print(f"API responded with an unexpected status: {response.status_code} - {response.text}",
                      file=sys.stderr)
                break

            json_data = response.json()
            status = json_data.get("export_status")

            if status == "finished" and "_links" in json_data:
                print('Download URL: ' + json_data["_links"]["api_url_to_repo"] + '/archive')
                print(json_data["_links"])
                return True

            time.sleep(5)

        print(f"Export failed, {response.text}", file=sys.stderr)
        return False

    def project_import(self, project_path, filepath):
        """ Import project to GitLab from file"""
        url_project_path = urllib.parse.quote(project_path, safe='')
        project_name = os.path.basename(project_path)
        namespace = os.path.dirname(project_path)

        # Import project
        print(f"Importing project {project_path}")
        response = self._api_import(project_name, namespace, filepath)
        if not 200 <= response.status_code < 300:
            print(f"Error during import: {response.status_code} {response.text}", file=sys.stderr)
            return False

        # Poll import status to check if import is successful
        while True:
            response = self._api_import_status(url_project_path)

            # Check API reply status
            if response.status_code != requests.codes.ok:
                print(f"Error during status check: {response.status_code} - {response.text}", file=sys.stderr)
                return False

            json_data = response.json()
            import_status = json_data.get("import_status")

            if import_status == "finished":
                return True
            elif import_status == "failed":
                print(f"Import failed, {response.text}", file=sys.stderr)
                return False

            # Wait a little bit
            time.sleep(1)

