import asyncio
from utils.rest import AsyncRestUtil


async def main():
    rest = AsyncRestUtil("config/config.yml")

    jobs = [
        {"jobName": "job1", "location": "log1.xml", "server": "111"},
        {"jobName": "job2", "location": "log2.xml", "server": "121"},
        {"jobName": "job3", "location": "log3.xml", "server": "133"}
    ]

    # =========================
    # 개별 job 단위 요청 실행 (PUT JSON 등)
    # =========================
    results = []

    for job in jobs:
        job_requests = [
            {
                "domain_name": "local",
                "api_name": "batch_patch",
                "body_params": {
                    "jobName": job["jobName"],
                    "location": job["location"],
                    "server": job["server"],
                },
            },
            # 필요시 GET 요청도 추가 가능
            # {
            #     "domain_name": "local",
            #     "api_name": "batch_query",
            #     "path_params": {"jobName": job["jobName"]},
            # },
        ]

        job_responses = await rest.call_all(job_requests)

        # job_responses 그대로 results에 추가
        results.extend(job_responses)

    # =========================
    # FINAL RESULT: 개별 요청 출력
    # =========================
    print("\n===== FINAL RESULT (Job Requests) =====")
    for r in results:
        header = f"API: {r.get('api_name', '')}, ReqID: {r.get('req_id', '')}, Job: {r.get('bind_params', {}).get('jobName', '')}"
        print(header)

        if r.get("error"):
            print("> ERROR:", r["error"])
        else:
            print(f"> Method: {r.get('method', '')}")
            print(f"> URL: {r.get('url', '')}")
            print(f"> Headers: {r.get('headers', '')}")
            print(f"> Params: {r.get('params', '')}")
            print(f"> Response Status: {r.get('response_status', '')}")
            print(f"> Response Body: {r.get('response_body', '')}")

        print("-" * 40)

    # =========================
    # 전체 job_names를 POST JSON 한 번에 보내기
    # =========================
    job_names = [job["jobName"] for job in jobs]

    save_responses = await rest.call_all([
        {
            "domain_name": "local",
            "api_name": "batch_save",
            "body_params": {"result": job_names},
        }
    ])

    # =========================
    # FINAL RESULT: batch_save 출력
    # =========================
    print("\n===== FINAL RESULT (Batch Save) =====")
    for r in save_responses:
        header = f"API: {r['api_name']}, ReqID: {r['req_id']}"
        print(header)

        if r.get("error"):
            print("> ERROR:", r["error"])
        else:
            print(f"> Method: {r['method']}")
            print(f"> URL: {r['url']}")
            print(f"> Headers: {r['headers']}")
            print(f"> Params: {r['params']}")
            print(f"> Response Status: {r['response_status']}")
            print(f"> Response Body: {r['response_body']}")

        print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
