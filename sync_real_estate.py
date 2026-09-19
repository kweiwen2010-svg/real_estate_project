import os
import requests
import pandas as pd
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("找不到 Supabase 金鑰！請確認是否已設定環境變數。")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 內政部各縣市 OpenData 英文代碼 (桃園: h, 台中: b, 嘉義市: i, 嘉義縣: q)
TARGET_CITIES = {
    '桃園市': 'h',
    '台中市': 'b',
    '嘉義市': 'i',
    '嘉義縣': 'q'
}

def fetch_and_clean_data():
    all_clean_data = []

    for city_name, code in TARGET_CITIES.items():
        print(f"正在從內政部平臺抓取 {city_name} (代碼: {code})...")
        # 改用內政部 OpenData 正式授權的穩定 CSV 下載點
        csv_url = f"https://opendata.land.moi.gov.tw/datainfo/opendataDownload?datasetPath=/{code.upper()}_LAND_BUILDING_C.csv"
        
        try:
            df = pd.read_csv(csv_url, encoding='utf-8', low_memory=False)
        except Exception as e:
            print(f"讀取 {city_name} 失敗: {e}")
            try:
                # 備用編碼嘗試
                df = pd.read_csv(csv_url, encoding='big5', low_memory=False)
            except Exception as e2:
                print(f"備用編碼讀取也失敗: {e2}")
                continue

        # 處理可能的欄位列位移
        if len(df) > 0 and '鄉鎮市區' not in df.columns and '本棟' not in str(df.columns):
            if len(df.columns) > 1:
                df.columns = df.iloc[0]
                df = df.iloc[1:].reset_index(drop=True)

        # 過濾親友特殊交易等雜訊
        if '備註' in df.columns:
            df = df[~df['備註'].astype(str).str.contains('親友|特殊|債權|偽造', na=False)]

        processed_rows = []
        for _, row in df.iterrows():
            try:
                district = str(row.get('鄉鎮市區', '')).strip()
                city_dist = f"{city_name}{district}"
                
                trans_sign = str(row.get('交易標的', ''))
                address = str(row.get('土地區段位置或街路名稱', ''))
                total_price = float(row.get('總價元', 0))
                
                building_ping = float(row.get('建物移轉總面積平方公尺', 0)) / 3.30578
                parking_price = float(row.get('車位總價元', 0))
                if pd.isna(parking_price): 
                    parking_price = 0
                    
                parking_ping = float(row.get('車位移轉總面積平方公尺', 0)) / 3.30578
                if pd.isna(parking_ping): 
                    parking_ping = 0

                if total_price <= 0 or building_ping <= 1:
                    continue

                net_building_ping = building_ping - parking_ping
                net_total_price = total_price - parking_price
                
                unit_price = (net_total_price / net_building_ping) if net_building_ping > 0 else 0

                trans_date = str(row.get('交易年月日', ''))
                building_type = str(row.get('建物型態', ''))
                room_hall = f"{row.get('建物房數', 0)}房{row.get('建物廳數', 0)}廳{row.get('建物衛數', 0)}衛"
                
                row_id = abs(hash(f"{city_dist}_{address}_{trans_date}_{total_price}"))

                processed_rows.append({
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
                    "transaction_date": trans_date
                })
            except Exception:
                continue

        all_clean_data.extend(processed_rows)

    print(f"總共清洗出 {len(all_clean_data)} 筆有效資料，準備上傳至 Supabase...")

    if len(all_clean_data) == 0:
        print("警告：本次抓取的有效資料為 0 筆！")
        return

    batch_size = 500
    for i in range(0, len(all_clean_data), batch_size):
        batch = all_clean_data[i:i+batch_size]
        supabase.table("real_estate_transactions").upsert(batch).execute()
        print(f"已上傳批次 {i} 至 {i+len(batch)}")
    print("資料同步完成！")

if __name__ == "__main__":
    fetch_and_clean_data()