import pandas as pd
import yaml
import os

# -------------------------------
# 설정 파일 읽기
# -------------------------------
def load_config(config_path="./config/config.yml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# -------------------------------
# 로그 기록 함수 (매 실행마다 새로 생성)
# -------------------------------
def write_log(log_path, text):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:  # ← append 아님, 항상 새로 생성
        f.write(text + "\n")

# -------------------------------
# 시스템 문자열이 리스트 중 하나라도 포함되는지 검사
# -------------------------------
def matches_any(system_value: str, key_list: list):
    if system_value is None:
        return False
    system_value = str(system_value)
    return any(key in system_value for key in key_list)

# -------------------------------
# 메인 처리 함수
# -------------------------------
def main():
    config = load_config()

    work_date = config["paths"]["work_date"]
    work_systems = config["paths"]["work_systems"]
    work_sources = config["paths"]["work_sources"]
    work_file = config["paths"]["work_file"]
    result_log = config["paths"]["work_result_file"]

    # → N/A 값이 NaN 으로 변환되지 않고 그대로 문자열 유지됨
    df = pd.read_excel(work_file, sheet_name="sheet1", keep_default_na=False)

    # 날짜 비교를 위해 문자열 변환
    df["반영일"] = df["반영일"].astype(str)

    # 날짜 필터 적용
    filtered = df[df["반영일"] == work_date]

    output_lines = []
    append = output_lines.append

    append("======================================")
    append(f"분석 결과 ({work_date})")
    append("======================================\n")

    # ---------------------------------------------------------
    # 1) work_systems 카운트
    # ---------------------------------------------------------
    append("■ 시스템별 건수")

    for system in work_systems:
        count = filtered[filtered["시스템"].apply(lambda x: matches_any(x, [system]))].shape[0]
        append(f"{system}: {count}건")

    append("\n")

    # ---------------------------------------------------------
    # 2) work_sources 분류 출력
    # ---------------------------------------------------------
    append("■ 소스 분류 결과")
    append(f"{work_date.replace('-', '')} 운영반영\n")

    for source in work_sources:
        append(f"[{source}]")

        rows = filtered[filtered["시스템"].apply(lambda x: matches_any(x, [source]))]

        if rows.empty:
            append("(데이터 없음)")
        else:
            for _, row in rows.iterrows():
                sr_no = row.get("SR리스트NO", "")
                sr_txt = row.get("SR", "")
                append(f"{sr_no}: {sr_txt}")   # ← 원본 그대로 출력

        append("")  # 줄바꿈

    # ---------------------------------------------------------
    # 3) 소스 목록 출력
    # ---------------------------------------------------------
    append("■ 소스 목록")

    for _, row in filtered.iterrows():
        src = row.get("소스", "")
        if src:
            append(src)

    # ---------------------------------------------------------
    # 결과 출력 + 파일 저장 (덮어쓰기)
    # ---------------------------------------------------------
    final_output = "\n".join(output_lines)

    print(final_output)
    write_log(result_log, final_output)


# -------------------------------
# 실행
# -------------------------------
if __name__ == "__main__":
    main()
