import io
import os
import zipfile
import pandas as pd
import requests
from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("找不到 Supabase 金鑰！")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 內政部當期免費開放資料 ZIP 檔網址
ZIP_URL = "https://plvr.land.moi.gov.tw/DownloadSeason?season=113S1&type=zip&fileName=lvr_landcsv.zip"

# 代碼對應檔名
CITY_FILES = {
    "桃園市": "h_lvr_land_a.csv",
    "台中市": "b_lvr_land_a.csv",
    "嘉義市": "i_lvr_land_a.csv",
    "嘉義縣": "q_lvr_land_a.csv",
}


def fetch_and_clean_data():
    all_clean_data = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    print("正在下載內政部實價登錄資料包...")
    resp = requests.get(
        "https://plvr.land.moi.gov.tw/Download?type=zip&fileName=lvr_landcsv.zip",
        headers=headers,
    )

    if resp.status_code != 200:
        print(f"下載 failure，狀態碼: {resp.status_code}")
        return

    # 解壓縮記憶體中的 ZIP
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        for city_name, csv_filename in CITY_FILES.items():
            if csv_filename not in z.namelist():
                print(f"找不到 {city_name} 的檔案: {csv_filename}")
                continue

            print(f"正在處理 {city_name}...")
            with z.open(csv_filename) as f:
                # header=0 抓第一列英文，skiprows=[1] 跳過第二列中文說明
                # 或者 skiprows=1 直接把第二列當 header
                try:
                    df = pd.read_csv(
                        f,
                        encoding="utf-8-sig",
                        header=0,
                        skiprows=[1],
                        low_memory=False,
                    )
                except Exception:
                    f.seek(0)
                    df = pd.read_csv(
                        f,
                        encoding="big5",
                        header=0,
                        skiprows=[1],
                        errors="ignore",
                        low_memory=False,
                    )

            # 備註過濾
            if "備註" in df.columns:
                df = df[
                    ~df["備註"]
                    .astype(str)
                    .str.contains("親友|特殊|債權|偽造", na=False)
                ]

            processed_rows = []
            for _, row in df.iterrows():
                try:
                    district = str(row.get("鄉鎮市區", "")).strip()
                    city_dist = f"{city_name}{district}"

                    trans_sign = str(row.get("交易標的", ""))
                    address = str(row.get("土地區段位置或街路名稱", ""))
                    total_price = float(row.get("總價元", 0))

                    building_ping = (
                        float(row.get("建物移轉總面積平方公尺", 0)) / 3.30578
                    )
                    parking_price = float(row.get("車位總價元", 0))
                    if pd.isna(parking_price):
                        parking_price = 0

                    parking_ping = (
                        float(row.get("車位移轉總面積平方公尺", 0)) / 3.30578
                    )
                    if pd.isna(parking_ping):
                        parking_ping = 0

                    if total_price <= 0 or building_ping <= 1:
                        continue

                    net_building_ping = building_ping - parking_ping
                    net_total_price = total_price - parking_price
                    unit_price = (
                        (net_total_price / net_building_ping)
                        if net_building_ping > 0
                        else 0
                    )

                    trans_date = str(row.get("交易年月日", ""))
                    building_type = str(row.get("建物型態", ""))
                    room_hall = f"{row.get('建物房數', 0)}房{row.get('建物廳數', 0)}廳{row.get('建物衛數', 0)}衛"

                    # 加上 building_ping 與 room_hall_health 讓 ID 更加唯一
row_id = abs(
    hash(
        f"{city_dist}_{address}_{trans_date}_{total_price}_{building_ping}_{room_hall}"
    )
)

                    processed_rows.append(
                        {
                            "id": str(row_id),
                            "city_district": city_dist,
                            "transaction_sign": trans_sign,
                            "address": address,
                            "total_price": total_price,
                            "building_ping": round(net_building_ping, 2),
                            "unit_price": round(unit_price, 0),
                            "parking_price": parking_price,
                            "parking_ping": round(parking_ping, 2),
                            "building_type": building_type,
                            "room_hall_health": room_hall,
                            "transaction_date": trans_date,
                        }
                    )
                except Exception:
                    continue

            all_clean_data.extend(processed_rows)

    print(
        f"總共清洗出 {len(all_clean_data)} 筆有效資料，準備上傳至 Supabase..."
    )

    if len(all_clean_data) == 0:
        print("警告：本次抓取的有效資料為 0 筆！")
        return

    # 【新增這段】透過字典去除同一個批次中重複的 id，避免 PostgreSQL UPSERT 衝突
    unique_data_dict = {item["id"]: item for item in all_clean_data}
    all_clean_data = list(unique_data_dict.values())

    print(
        f"去重後剩餘 {len(all_clean_data)} 筆唯一資料，準備上傳至 Supabase..."
    )

    batch_size = 500
    for i in range(0, len(all_clean_data), batch_size):
        batch = all_clean_data[i : i + batch_size]
        supabase.table("real_estate_transactions").upsert(batch).execute()
        print(f"已上傳批次 {i} 至 {i+len(batch)}")
    print("資料同步完成！")


if __name__ == "__main__":
    fetch_and_clean_data()