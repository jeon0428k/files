import os
import requests

BASE_URL = "https://jira.your-company.com"
PAT = os.environ["JIRA_PAT"]  # 개인 토큰
CA_PEM = "/path/to/your_company_ca.pem"  # 사내 CA면 지정 (없으면 True)

session = requests.Session()
session.headers.update({
    "Accept": "application/json",
    "Authorization": f"Bearer {PAT}",
})

def jira_get(path, params=None):
    r = session.get(
        f"{BASE_URL}{path}",
        params=params,
        timeout=20,
        verify=CA_PEM,   # 사내 인증서면 CA pem/crt 경로
    )
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    me = jira_get("/rest/api/2/myself")
    print(me.get("displayName"))

    issues = jira_get("/rest/api/2/search", params={
        "jql": "assignee = currentUser() ORDER BY updated DESC",
        "maxResults": 5
    })
    print([i["key"] for i in issues.get("issues", [])])