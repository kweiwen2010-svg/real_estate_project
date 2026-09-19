import pandas as pd
import streamlit as st
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🏠 實價登錄自動同步儀表板")
st.write("資料來源：內政部實價登錄 ➡️ Supabase")


@st.cache_data(ttl=600)
def load_data():
    # 抓取最多 5000 筆資料
    response = (
        supabase.table("real_estate_transactions")
        .select("*")
        .limit(5000)
        .execute()
    )
    return pd.DataFrame(response.data)


df = load_data()

if not df.empty:
    st.success(f"目前資料庫共有 {len(df)} 筆資料")

    # 🔍 建立搜尋關鍵字輸入框
    search_term = st.text_input(
        "🔎 請輸入關鍵字查詢（例如：台中文心路、桃園市、車位）：", ""
    )

    # 執行資料過濾
    if search_term:
        # 將「縣市區域」與「路段地址」合併搜尋，只要包含關鍵字就列出
        filtered_df = df[
            df["city_district"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
            | df["address"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
        ]
        st.write(f"搜尋 **「{search_term}」**，共找到 {len(filtered_df)} 筆結果：")
        st.dataframe(filtered_df, use_container_width=True)
    else:
        # 未輸入關鍵字時顯示全部資料
        st.dataframe(df, use_container_width=True)

else:
    st.warning("目前資料庫中沒有資料，請確認資料同步狀態。")