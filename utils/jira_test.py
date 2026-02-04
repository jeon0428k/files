import requests

API_URL = "https://api.example.com/v1/health"
CA_CRT_PATH = "./files/ca_bundle.crt"  # 서버 인증서 검증에 사용할 CA(또는 체인) crt
CA_PEM_PATH = "./files/ca_bundle.pem"

CLIENT_CERT_PEM = "./files/client_cert.pem"
CLIENT_KEY_PEM = "./files/client_key.pem"


def call_api_with_ca_verify():
    try:
        r = requests.get(
            API_URL,
            timeout=10,
            verify=CA_CRT_PATH,  # 여기 핵심: 시스템 CA 대신 내가 가진 crt로 검증
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.SSLError as e:
        raise RuntimeError(f"TLS 검증 실패(SSLError): {e}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"요청 실패: {e}") from e


def call_api_with_pem_verify():
    r = requests.get(
        API_URL,
        timeout=10,
        verify=CA_PEM_PATH,  # 👈 CA 인증서 또는 체인 pem
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    return r.json()

def call_api_with_mtls_pem():
    r = requests.post(
        API_URL,
        json={"message": "hello"},
        timeout=10,
        cert=(CLIENT_CERT_PEM, CLIENT_KEY_PEM),  # 👈 pem + pem
        verify=CA_PEM_PATH,
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    print(call_api_with_ca_verify())
    print(call_api_with_pem_verify())
    print(call_api_with_mtls_pem())
