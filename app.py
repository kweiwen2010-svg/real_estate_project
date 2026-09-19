import pandas as pd
import streamlit as st
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="實價登錄查詢儀表板", layout="wide")

st.title("🏠 實價登錄自動同步儀表板")
st.write("資料來源：內政部實價登錄 ➡️ Supabase")


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


if st.button("🔄 強制刷新最新資料"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    st.sidebar.header("🎯 條件篩選器")
    search_term = st.sidebar.text_input(
        "🔎 關鍵字搜尋（路名/區域/建物型態）：", ""
    )

    # 數據轉型與清洗
    df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce").fillna(
        0
    )
    df["building_ping"] = pd.to_numeric(
        df["building_ping"], errors="coerce"
    ).fillna(0)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(
        0
    )

    # 計算每坪單價（萬元/坪）以方便展示圖表
    df["unit_price_wan"] = df["unit_price"] / 10000

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

    # 執行篩選
    filtered_df = df[
        (df["total_price"] >= price_range[0])
        & (df["total_price"] <= price_range[1])
        & (df["building_ping"] >= ping_range[0])
        & (df["building_ping"] <= ping_range[1])
    ].copy()

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

    st.success(f"目前成功載入 {len(df)} 筆完整資料！")

    # ------------------ 📈 新增：統計指標卡片 ------------------
    st.subheader("📊 篩選行情統計")

    # 排除單價為 0 的異常值進行統計
    valid_unit_price = filtered_df[filtered_df["unit_price_wan"] > 0][
        "unit_price_wan"
    ]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        avg_unit_price = (
            valid_unit_price.mean() if not valid_unit_price.empty else 0
        )
        st.metric("平均單價", f"{avg_unit_price:.2f} 萬/坪")

    with col2:
        avg_total_price = (
            filtered_df["total_price"].mean() / 10000
            if not filtered_df.empty
            else 0
        )
        st.metric("平均總價", f"{avg_total_price:.1f} 萬元")

    with col3:
        max_unit = valid_unit_price.max() if not valid_unit_price.empty else 0
        st.metric("最高單價", f"{max_unit:.2f} 萬/坪")

    with col4:
        min_unit = valid_unit_price.min() if not valid_unit_price.empty else 0
        st.metric("最低單價", f"{min_unit:.2f} 萬/坪")

    st.markdown("---")

    # ------------------ 📈 新增：價格分佈圖表 ------------------
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("📈 單價區間分佈（萬/坪）")
        if not valid_unit_price.empty:
            # 將單價切分為區間，統計數量
            counts, bin_edges = pd.cut(
                valid_unit_price, bins=15, retbins=True
            )
            chart_data = (
                counts.value_counts()
                .sort_index()
                .reset_index(name="筆數")
            )
            chart_data["單價區間"] = chart_data["index"].astype(str)
            st.bar_chart(
                chart_data.set_index("單價區間")["筆數"],
                color="#FF4B4B",
            )
        else:
            st.info("尚無單價資料可繪製圖表。")

    with col_chart2:
        st.subheader("📌 面積 vs 總價分佈圖")
        if not filtered_df.empty:
            # 轉換為萬元以方便檢視
            chart_df = filtered_df[
                (filtered_df["building_ping"] > 0)
                & (filtered_df["total_price"] > 0)
            ].copy()
            chart_df["總價(萬元)"] = chart_df["total_price"] / 10000
            chart_df["坪數"] = chart_df["building_ping"]

            st.scatter_chart(
                chart_df, x="坪數", y="總價(萬元)", color="#1F77B4"
            )
        else:
            st.info("尚無資料可繪製圖表。")

    st.markdown("---")

    # 顯示詳細數據表格
    st.subheader(f"📋 詳細成交列表（共 {len(filtered_df)} 筆）")
    st.dataframe(filtered_df, use_container_width=True)

else:
    st.warning("目前資料庫中沒有資料，請確認資料同步狀態。")