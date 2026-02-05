import pandas as pd
import yaml
import os
import sys
from datetime import datetime

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
# 텍스트 파일 기록 함수 (매 실행마다 새로 생성)
# -------------------------------
def write_text_file(file_path, lines):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))

# -------------------------------
# 공백(whitespace) 제거
# -------------------------------
def remove_all_spaces(value):
    if value is None:
        return ""
    # 모든 공백류(스페이스/탭/개행 포함) 제거
    return "".join(str(value).split())

# -------------------------------
# 실행 인자 날짜 파싱
#   - YYYYMMDD -> YYYY-MM-DD
#   - MMDD     -> {현재년도}-MM-DD
# -------------------------------
def parse_work_date(arg_date: str):
    arg_date = str(arg_date).strip()

    # YYYYMMDD
    if len(arg_date) == 8 and arg_date.isdigit():
        return f"{arg_date[:4]}-{arg_date[4:6]}-{arg_date[6:8]}"

    # MMDD → 현재년도-MM-DD
    if len(arg_date) == 4 and arg_date.isdigit():
        year = datetime.now().year
        return f"{year}-{arg_date[:2]}-{arg_date[2:4]}"

    raise ValueError(f"Invalid date argument: {arg_date}")

# -------------------------------
# 시스템 문자열이 리스트 중 하나라도 포함되는지 검사
# -------------------------------
def matches_any(system_value: str, key_list: list):
    if not system_value:
        return False
    tokens = str(system_value).split("-")
    # 토큰이 key와 완전히 일치하는 경우에만 매칭
    return any(token == key for token in tokens for key in key_list)

# -------------------------------
# 메인 처리 함수
# -------------------------------
def main():
    config = load_config()

    # ---------------------------------------------------------
    # work_date 결정
    #   - argument 있으면 argument 사용
    #   - 없으면 config 값 사용
    # ---------------------------------------------------------
    if len(sys.argv) > 1:
        work_date = parse_work_date(sys.argv[1])
    else:
        work_date = config["paths"]["work_date"]

    work_systems = config["paths"]["work_systems"]
    work_sources = config["paths"]["work_sources"]
    work_file = config["paths"]["work_file"]
    result_log = config["paths"]["work_result_file"]

    # 옵션: 소스 목록을 worklist_file에 저장할지 여부
    is_write_worklist = bool(config.get("is_write_worklist", False))
    worklist_file_path = config["paths"]["worklist_file"]

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

    # 전체 건수 추가
    total_count = filtered.shape[0]
    append(f"전체: {total_count}건")

    # 개별 시스템별 건수 출력
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
    # 3) 소스 목록 출력 (+ 공백 제거) + (옵션 시 파일 저장)
    # ---------------------------------------------------------
    append("■ 소스 목록")

    source_lines = []
    for _, row in filtered.iterrows():
        src = row.get("소스", "")
        if src:
            cleaned = remove_all_spaces(src)  # 공백 제거
            if cleaned:
                append(cleaned)               # 출력도 공백 없이
                source_lines.append(cleaned)  # 파일 저장용

    # 옵션이 true면 worklist_file에 저장 (덮어쓰기)
    if is_write_worklist:
        write_text_file(worklist_file_path, source_lines)

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
