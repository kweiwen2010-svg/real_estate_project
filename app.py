import streamlit as st
from supabase import create_client
import pandas as pd

# 讀取 Supabase 連線資訊 (之後會設定在 Streamlit 雲端後台)
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🏠 實價登錄自動同步儀表板")
st.write("資料來源：內政部實價登錄 ➡️ Supabase")

# 從 Supabase 抓取資料 (請把 real_estate_data 換成你的實際資料表名稱)
@st.cache_data
def load_data():
    response = supabase.table("real_estate_transactions").select("*").execute()
    return pd.DataFrame(response.data)

df = load_data()

if not df.empty:
    # 顯示資料筆數
    st.success(f"目前資料庫共有 {len(df)} 筆實價登錄資料")
    
    # 顯示互動式表格（支援手機左右滑動、排序、搜尋）
    st.dataframe(df, use_container_width=True)
else:
    st.warning("目前資料庫中沒有資料，請先確認 GitHub Actions 是否成功同步。")