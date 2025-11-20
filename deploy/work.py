import pandas as pd
import yaml
import os

def load_config(config_path: str):
    """YAML 설정 파일 로드"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_work_sheet(excel_path: str, sheet_name: str = "sheet1"):
    """엑셀 파일에서 sheet1 읽기"""
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"엑셀 파일이 존재하지 않습니다: {excel_path}")
    return pd.read_excel(excel_path, sheet_name=sheet_name)

def filter_by_date(df: pd.DataFrame, target_date: str):
    """날짜 컬럼으로 필터링"""
    # 날짜가 datetime 형식일 경우 문자열 변환 후 비교
    df["날짜"] = df["날짜"].astype(str)
    return df[df["날짜"] == target_date]

def analyze_filtered_rows(df: pd.DataFrame):
    """구분 건수 및 sr id + 내용 출력"""
    result = {}

    # 구분 컬럼 별 건수
    category_count = df["구분"].value_counts().to_dict()
    result["category_count"] = category_count

    # sr id, 내용 목록
    items = []
    for _, row in df.iterrows():
        items.append({
            "id": row["id"],
            "구분": row["구분"],
            "sr_id": row["sr id"],
            "내용": row["내용"]
        })
    result["items"] = items
    return result

def main():
    # 1) config.yml 로드
    config = load_config("config/config.yml")
    excel_path = config["paths"]["work_file"]
    target_date = config["paths"]["work_date"]

    # 2) 엑셀 sheet1 읽기
    df = load_work_sheet(excel_path, sheet_name="sheet1")

    # 3) 날짜로 필터링
    filtered_df = filter_by_date(df, target_date)

    # 4) 분석 실행
    analysis = analyze_filtered_rows(filtered_df)

    # 5) 결과 출력
    print("=== 구분별 건수 ===")
    for k, v in analysis["category_count"].items():
        print(f"{k}: {v} 건")

    print("\n=== 상세 목록 (sr id / 내용) ===")
    for item in analysis["items"]:
        print(f"- id: {item['id']}, 구분: {item['구분']}, sr id: {item['sr_id']}, 내용: {item['내용']}")

if __name__ == "__main__":
    main()
