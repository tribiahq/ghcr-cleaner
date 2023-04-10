# Standard lib
from typing import Iterable, Any
from urllib.parse import urljoin
from functools import cache
import argparse
import json
import sys
import os

# Third party
import requests
from dxf import DXF


def str2bool(value: str) -> bool:
    """Utility to convert a boolean string representation to a boolean object."""
    if str(value).lower() in ("yes", "true", "y", "1", "on"):
        return True
    elif str(value).lower() in ("no", "false", "n", "0", "off"):
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected.")


def get_args():
    """Get all arguments passed into this script."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token", type=str, required=True,
        help="Github Personal access token with delete:packages permissions",
    )
    parser.add_argument(
        "--repo-owner", type=str.lower, required=True,
        help="The repository owner name",
    )
    parser.add_argument(
        "--repo-name", type=str.lower, required=False, nargs="?", const="", default="",
        help="Delete containers only from this repository",
    )
    parser.add_argument(
        "--package-name", type=str.lower, required=False, nargs="?", const="", default="",
        help="Delete only package name",
    )
    parser.add_argument(
        "--owner-type", type=str.lower, choices=["org", "user"], default="org",
        help="Owner type (org or user)",
    )
    parser.add_argument(
        "--dry-run", type=str2bool, default=False,
        help="Run the script without making any changes.",
    )

    args = parser.parse_args()

    # GitHub offers the repository as an owner/repo variable
    # So we need to handle that case
    if "/" in args.repo_name:
        owner, repo_name = args.repo_name.lower().split("/")
        if owner != args.owner:
            msg = f"Mismatch in repository: {args.repo_name} and owner:{args.repository_owner}"
            raise ValueError(msg)
        args.repo_name = repo_name

    # Strip any leading or trailing '/'
    args.package_name = args.package_name.strip("/")
    return args


_args = get_args()
PER_PAGE = 100
DOCKER_ENDPOINT = "ghcr.io"
API_ENDPOINT = os.environ.get("GITHUB_API_URL", "https://api.github.com")
GITHUB_TOKEN = _args.token
DRY_RUN = _args.dry_run


def request_github_api(url: str, method="GET", **options) -> requests.Response:
    """Make web request to GitHub API, returning response."""
    return requests.request(
        method, url,
        headers={
            "X-GitHub-Api-Version": "2022-11-28",
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
        },
        **options
    )


def get_paged_resp(url: str, params: dict[str, Any] = None) -> Iterable[dict]:
    """Return an iterator of paged results, looping until all resources are collected."""
    params = params or {}
    params.update(page="1")
    params.setdefault("per_page", min(PER_PAGE, 100))
    url = urljoin(API_ENDPOINT, url)

    while True:
        if not (resp := request_github_api(url, params=params)):
            print(url)
            raise Exception(resp.text[:50])

        yield from resp.json()

        # Continue with next page if one is found
        if "next" in resp.links:
            url = resp.links["next"]["url"]
            params.pop("page", None)
        else:
            break


class TC:
    """Ascii color codes."""
    OKGREEN = lambda x: f"\033[92m{x}\033[0m"
    OKBLUE = lambda x: f"\033[94m{x}\033[0m"
    OKCYAN = lambda x: f"\033[96m{x}\033[0m"
    WARNING = lambda x: f"\033[93m{x}\033[0m"
    FAIL = lambda x: f"\033[91m{x}\033[0m"


class Version:
    def __init__(self, pkg: "Package", version):
        self.version = version
        self.pkg = pkg

    @property
    def id(self):
        return self.version["id"]

    @property
    def name(self) -> str:
        return self.version["name"]

    @property
    def tags(self) -> list[str]:
        """Return list of tags for this version."""
        return self.version["metadata"]["container"]["tags"]

    @cache
    def get_deps(self) -> list[str]:
        """Return list of untagged images that this version depends on."""
        if self.tags:
            manifest = self.pkg.registry.get_manifest(self.name)
            manifest = json.loads(manifest)
            return [arch["digest"] for arch in manifest.get("manifests", [])]
        else:
            return []

    def delete(self):
        """Delete this image version from the registry."""
        print(TC.WARNING("Deleting"), f"{self.name}:", end=" ")
        if DRY_RUN:
            print(TC.OKGREEN("Dry Run"))
            return True

        try:
            resp = request_github_api(self.version["url"], method="DELETE")
        except requests.RequestException as e:
            print(e.response.reason if e.response else "Fatal error")
            return False
        else:
            print(TC.OKGREEN("OK") if resp.status_code == 204 else resp.reason)
            return resp.ok

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        else:
            return False


class Package:
    def __init__(self, owner: str, pkg_data):
        self.pkg = pkg_data
        self.owner = owner

        self.registry = DXF(
            DOCKER_ENDPOINT,
            repo=f"{self.owner}/{self.name}",
            auth=lambda dxf, resp: dxf.authenticate(owner, GITHUB_TOKEN, response=resp)
        )

    @property
    def name(self) -> str:
        return self.pkg["name"]

    @property
    def version_url(self) -> str:
        """Rest url to package versions."""
        url = self.pkg["url"]
        return f"{url}/versions"

    def get_versions(self) -> Iterable["Version"]:
        """Iterable of package versions."""
        for version in get_paged_resp(self.version_url):
            yield Version(self, version)

    @classmethod
    def get_all_packages(cls, owner_type: str, owner: str, repo_name: str, package_name: str) -> Iterable["Package"]:
        """Return an iterator of registry packages."""
        path = f"/{owner_type}s/{owner}/packages?package_type=container"
        for pkg in get_paged_resp(path):
            if repo_name and pkg.get("repository", {}).get("name", "").lower() != repo_name.lower():
                continue

            elif package_name and pkg["name"] != package_name:
                continue

            yield cls(owner, pkg)


def bulk_delete(delete_list: Iterable[Version]):
    status_counts = [0, 0]  # [Fail, OK]
    for unwanted_version in delete_list:
        status = unwanted_version.delete()
        status_counts[status] += 1

    print("")
    print(status_counts[1], TC.OKGREEN("Deletions"))
    print(status_counts[0], TC.FAIL("Errors"))
    if status_counts[0]:
        sys.exit(1)


def run() -> Iterable[Version]:
    # Get list of all packages
    all_packages = Package.get_all_packages(
        owner=_args.repo_owner,
        repo_name=_args.repo_name,
        package_name=_args.package_name,
        owner_type=_args.owner_type,
    )

    for pkg in all_packages:
        count = 0
        all_deps, all_untagged = set(), set()
        print(TC.OKCYAN("Processing package:"), TC.OKBLUE(pkg.name), end="... ")
        for count, version in enumerate(pkg.get_versions(), start=1):
            deps = version.get_deps()
            all_deps.update(deps)
            if not version.tags:
                all_untagged.add(version)

        # Collect list of all untagged versions that are not dependencies of other versions
        unwanted = [version for version in all_untagged if version.name not in all_deps]
        print(
            f"({TC.OKGREEN('total')}={count},",
            f"{TC.OKGREEN('tagged')}={count - len(all_untagged)},",
            f"{TC.OKGREEN('untagged')}={len(all_untagged)},",
            f"{TC.OKGREEN('unwanted')}={len(unwanted)})",
        )
        yield from unwanted


if __name__ == "__main__":
    _delete_list = run()
    bulk_delete(_delete_list)
