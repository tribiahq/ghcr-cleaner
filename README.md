# delete-untagged-ghcr-action V2
[![test](https://github.com/quartx-analytics/delete-untagged-ghcr-action/actions/workflows/test.yml/badge.svg)](https://github.com/quartx-analytics/delete-untagged-ghcr-action/actions/workflows/test.yml)

Action for deleting containers from Github container registry.

Deletes all truly untagged ghcr containers in a repository. Tags that are not depended on by other tags
will be deleted. This scenario can happen when using multiplatform packages.

## Usage

<!-- start usage -->
```yaml
- name: Delete untagged GHCR
  uses: quartx-analytics/delete-untagged-ghcr-action@v2
  with:
    # Personal access token (PAT) used to fetch the repository. The PAT is configured
    # with the local git config, which enables your scripts to run authenticated git
    # commands. The post-job step removes the PAT.
    # needs delete:packages permissions
    # required: true
    # [Learn more about creating and using encrypted secrets](https://help.github.com/en/actions/automating-your-workflow-with-github-actions/creating-and-using-encrypted-secrets)
    token: ${{ secrets.PAT_TOKEN }}
    # 'The repository owner name'
    # Default: ${{ github.repository_owner }}
    repository-owner: ''
    # Repository name or name with owner
    # Delete only from repository name
    repository-name: ''
    # 'The package name'
    # Delete only from package name
    # required: false
    package_name: ''
    # the owner type
    # required: true
    # choices: org, user
    owner_type: ''

```
<!-- end usage -->

## Delete all containers from repository without tags except untagged multiplatform packages
```yaml
- name: Delete all containers from repository without tags
  uses: quartx-analytics/delete-untagged-ghcr-action@v2
  with:
    token: ${{ secrets.PAT_TOKEN }}
    repository_owner: ${{ github.repository_owner }}
    repository-name: ${{ github.repository }}
    owner-type: org # or user

```


## Delete all containers from package without tags except untagged multiplatform packages
```yaml
- name: Delete all containers from package without tags
    uses: quartx-analytics/delete-untagged-ghcr-action@v2
    with:
        token: ${{ secrets.PAT_TOKEN }}
        repository_owner: ${{ github.repository_owner }}
        package_name: the-package-name
        owner-type: org # or user
```
