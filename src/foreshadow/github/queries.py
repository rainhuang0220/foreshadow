"""GraphQL documents copied from docs/p0-architecture.md (Discovery / Hydrate).

Every connection has ``first:``. There is no ``watchers`` field.
"""

REPO_A_FIELDS = """
fragment RepoA on Repository {
  id
  databaseId
  nameWithOwner
  url
  description
  createdAt
  pushedAt
  updatedAt
  isFork
  isArchived
  isDisabled
  isEmpty
  isTemplate
  isMirror
  hasIssuesEnabled
  stargazerCount
  forkCount
  primaryLanguage { name }
  licenseInfo { spdxId key }
  repositoryTopics(first: 20) { nodes { topic { name } } }
  defaultBranchRef {
    name
    target { ... on Commit { oid committedDate } }
  }
  issuesOpen: issues(states: OPEN, first: 1) { totalCount }
  issuesClosed: issues(states: CLOSED, first: 1) { totalCount }
  prsOpen: pullRequests(states: OPEN, first: 1) { totalCount }
  discussions(first: 1) { totalCount }
  contributing: object(expression: "HEAD:CONTRIBUTING.md") { ... on Blob { byteSize } }
}
""".strip()

REPO_B_FIELDS = """
fragment RepoB on Repository {
  ...RepoA
  readme: object(expression: "HEAD:README.md") {
    ... on Blob { text byteSize }
  }
  issuesOpenSample: issues(states: OPEN, first: 100) {
    totalCount
    nodes {
      number
      title
      createdAt
      author { login }
      authorAssociation
      labels(first: 8) { nodes { name } }
      comments(first: 3) {
        totalCount
        nodes { author { login } authorAssociation createdAt }
      }
      assignees(first: 1) { totalCount }
    }
  }
  prsMerged: pullRequests(states: MERGED, first: 20, orderBy: {field: UPDATED_AT, direction: DESC}) {
    nodes {
      number
      createdAt
      mergedAt
      author { login }
      authorAssociation
      reviews(first: 1) { totalCount }
    }
  }
  issuesClosedSample: issues(states: CLOSED, first: 30) {
    nodes { title }
  }
  gfi: issues(states: OPEN, labels: ["good first issue"], first: 1) { totalCount }
  gfiHyphen: issues(states: OPEN, labels: ["good-first-issue"], first: 1) { totalCount }
  helpWanted: issues(states: OPEN, labels: ["help wanted"], first: 1) { totalCount }
  helpWantedHyphen: issues(states: OPEN, labels: ["help-wanted"], first: 1) { totalCount }
}
""".strip()

SEARCH_REPOS = """
query SearchRepos($q: String!, $n: Int!) {
  rateLimit { cost remaining limit resetAt }
  search(type: REPOSITORY, query: $q, first: $n) {
    repositoryCount
    pageInfo { hasNextPage }
    nodes {
      ... on Repository {
        id
        databaseId
        nameWithOwner
        url
        description
        createdAt
        pushedAt
        updatedAt
        isFork
        isArchived
        isDisabled
        isEmpty
        isMirror
        hasIssuesEnabled
        stargazerCount
        forkCount
        primaryLanguage { name }
        licenseInfo { spdxId key }
        repositoryTopics(first: 10) { nodes { topic { name } } }
      }
    }
  }
}
""".strip()

HYDRATE_A = f"""
{REPO_A_FIELDS}

query HydrateA($owner: String!, $name: String!) {{
  rateLimit {{ cost remaining limit resetAt }}
  repository(owner: $owner, name: $name, followRenames: true) {{
    ...RepoA
  }}
}}
""".strip()

HYDRATE_A_NODE = f"""
{REPO_A_FIELDS}

query HydrateANode($id: ID!) {{
  rateLimit {{ cost remaining limit resetAt }}
  node(id: $id) {{
    ... on Repository {{ ...RepoA }}
  }}
}}
""".strip()

HYDRATE_B = f"""
{REPO_A_FIELDS}

{REPO_B_FIELDS}

query HydrateB($owner: String!, $name: String!) {{
  rateLimit {{ cost remaining limit resetAt }}
  repository(owner: $owner, name: $name, followRenames: true) {{ ...RepoB }}
}}
""".strip()

HYDRATE_B_NODE = f"""
{REPO_A_FIELDS}

{REPO_B_FIELDS}

query HydrateBNode($id: ID!) {{
  rateLimit {{ cost remaining limit resetAt }}
  node(id: $id) {{ ... on Repository {{ ...RepoB }} }}
}}
""".strip()

HYDRATE_B_STRIPPED = f"""
{REPO_A_FIELDS}

query HydrateBStripped($id: ID!) {{
  rateLimit {{ cost remaining limit resetAt }}
  node(id: $id) {{
    ... on Repository {{
      ...RepoA
      gfi: issues(states: OPEN, labels: ["good first issue"], first: 1) {{ totalCount }}
      helpWanted: issues(states: OPEN, labels: ["help wanted"], first: 1) {{ totalCount }}
    }}
  }}
}}
""".strip()
