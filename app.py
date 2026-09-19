import pandas as pd
import streamlit as st
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="實價登錄查詢儀表板", layout="wide")

st.title("🏠 實價登錄自動同步儀表板")
st.write("資料來源：內政部實價登錄 ➡️ Supabase")


# 分頁抓取：自動突破 1000 筆限制
@st.cache_data(ttl=600)
def load_data():
    all_rows = []
    step = 1000
    start = 0

    while True:
        response = (
            supabase.table("real_estate_transactions")
            .select("*")
            .range(start, start + step - 1)
            .execute()
        )
        data = response.data
        if not data:
            break

        all_rows.extend(data)

        if len(data) < step:
            break

        start += step

    return pd.DataFrame(all_rows)


# 按鈕：可直接手動強制刷新快取
if st.button("🔄 強制刷新最新資料"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    st.success(f"目前成功載入 {len(df)} 筆實價登錄資料！")

    # 側邊欄篩選
    st.sidebar.header("🎯 條件篩選器")
    search_term = st.sidebar.text_input(
        "🔎 關鍵字搜尋（路名/區域/建物型態）：", ""
    )

    df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce").fillna(
        0
    )
    df["building_ping"] = pd.to_numeric(
        df["building_ping"], errors="coerce"
    ).fillna(0)

    min_price, max_price = float(df["total_price"].min()), float(
        df["total_price"].max()
    )
    min_ping, max_ping = float(df["building_ping"].min()), float(
        df["building_ping"].max()
    )

    price_range = st.sidebar.slider(
        "💰 總價範圍 (元)：",
        min_value=int(min_price),
        max_value=int(max_price),
        value=(int(min_price), int(max_price)),
        step=500000,
    )

    ping_range = st.sidebar.slider(
        "📐 建物面積範圍 (坪)：",
        min_value=int(min_ping),
        max_value=int(max_ping),
        value=(int(min_ping), int(max_ping)),
        step=5,
    )

    filtered_df = df[
        (df["total_price"] >= price_range[0])
        & (df["total_price"] <= price_range[1])
        & (df["building_ping"] >= ping_range[0])
        & (df["building_ping"] <= ping_range[1])
    ]

    if search_term:
        filtered_df = filtered_df[
            filtered_df["city_district"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
            | filtered_df["address"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
            | filtered_df["building_type"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
        ]

    st.write(f"📊 篩選結果：共 **{len(filtered_df)}** 筆資料")
    st.dataframe(filtered_df, use_container_width=True)
else:
    st.warning("目前資料庫中沒有資料，請確認資料同步狀態。")