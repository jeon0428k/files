import asyncio
from utils.rest import AsyncRestUtil


async def main():
    rest = AsyncRestUtil("config/config.yml")

    results = await rest.call_all([

        # =========================
        # GET
        # =========================
        {
            "domain_name": "local",
            "api_name": "batch_query",
            "path_params": {"jobName": "test1"},
        },

        # =========================
        # POST JSON (inline)
        # =========================
        {
            "domain_name": "local",
            "api_name": "batch_save",
            "body_params": {
                "jobName": "test1",
                "param1": "A",
                "param2": "B",
                "param3": "C",
                "name": "junghwan"
            },
        },

        # =========================
        # PUT JSON (file)
        # =========================
        {
            "domain_name": "local",
            "api_name": "batch_patch_from_file",
        },

        # =========================
        # POST TEXT (inline)
        # =========================
        {
            "domain_name": "local",
            "api_name": "send_text",
            "body_params": {
                "message": "hello world"
            },
        },

        # =========================
        # POST TEXT (file)
        # =========================
        {
            "domain_name": "local",
            "api_name": "send_text_from_file",
        },

        # =========================
        # POST JSON + AUTH
        # =========================
        {
            "domain_name": "external",
            "api_name": "save_data",
            "body_params": {
                "id": "1001",
                "name": "tester"
            },
            "header_params": {
                "token": "ACCESS_TOKEN"
            }
        },

        # =========================
        # MULTIPART (single file)
        # =========================
        {
            "domain_name": "external",
            "api_name": "upload_single_file",
            "body_params": {
                "filePath": "/tmp/a.txt"
            },
            "header_params": {
                "token": "ACCESS_TOKEN"
            }
        },

        # =========================
        # MULTIPART (multi file + data)
        # =========================
        {
            "domain_name": "external",
            "api_name": "upload_multi_file",
            "body_params": {
                "filePath1": "/tmp/a.txt",
                "filePath2": "/tmp/b.txt",
                "userId": "1001",
                "description": "batch upload"
            },
            "header_params": {
                "token": "ACCESS_TOKEN"
            }
        },

        # =========================
        # DELETE
        # =========================
        {
            "domain_name": "external",
            "api_name": "delete_data",
            "path_params": {
                "id": "1001"
            },
            "header_params": {
                "token": "ACCESS_TOKEN"
            }
        },
    ])

    print("\n===== FINAL RESULT =====")
    for r in results:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
