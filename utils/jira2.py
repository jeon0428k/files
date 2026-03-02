from jira import JIRA
import os

JIRA_URL = "https://jira.your-company.com"
PAT = os.environ["JIRA_PAT"]

options = {
    "server": JIRA_URL,
    "verify": "/path/to/company_ca.pem",  # 사내 CA 없으면 True
}

jira = JIRA(
    options=options,
    token_auth=PAT,   # ⭐ Data Center PAT 방식
)

# 로그인 확인
me = jira.current_user()
print("current user:", me)

# 내 이슈 검색
issues = jira.search_issues(
    "assignee = currentUser() ORDER BY updated DESC",
    maxResults=5
)

for issue in issues:
    print(issue.key, "-", issue.fields.summary)