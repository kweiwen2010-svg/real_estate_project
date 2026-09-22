import pandas as pd
import streamlit as st
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="實價登錄分區分析儀表板", layout="wide")

st.title("🏠 實價登錄分區行情儀表板")
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
    # 1. 數據清洗與欄位轉換
    df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce").fillna(
        0
    )
    df["building_ping"] = pd.to_numeric(
        df["building_ping"], errors="coerce"
    ).fillna(0)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(
        0
    )

    # 清洗：過濾掉負數與極端不合理的數據（例如坪數 <= 0 或 > 300 坪的非一般住宅）
    df = df[(df["building_ping"] > 0) & (df["building_ping"] <= 300)].copy()

    # 換算單位：總價改為「萬元」、單價改為「萬/坪」
    df["total_price_wan"] = df["total_price"] / 10000
    df["unit_price_wan"] = df["unit_price"] / 10000

    # 側邊欄條件篩選器
    st.sidebar.header("🎯 區域與條件篩選")

    # 行政區選擇
    available_districts = sorted(
        [
            d
            for d in df["city_district"].dropna().unique()
            if str(d).strip() != ""
        ]
    )
    selected_district = st.sidebar.selectbox(
        "📍 選擇縣市行政區（例如：嘉義縣中埔鄉）：",
        ["全部區域"] + available_districts,
    )

    # 關鍵字搜尋
    search_term = st.sidebar.text_input(
        "🔎 關鍵字 / 路名搜尋（例如：中正路）：", ""
    )

    # 計算合理的動態滑桿範圍（單位：萬元、坪）
    max_p_wan = (
        int(df["total_price_wan"].max())
        if not df.empty
        else 10000
    )
    max_p_wan = min(max_p_wan, 10000)  # 最高上限設為 1 億（10000 萬）

    max_ping_val = (
        int(df["building_ping"].max()) if not df.empty else 100
    )
    max_ping_val = min(max_ping_val, 200)  # 最高坪數設為 200 坪

    # 2. 優化後的直覺滑桿
    price_range = st.sidebar.slider(
        "💰 總價範圍 (萬元)：",
        min_value=0,
        max_value=max_p_wan,
        value=(0, max_p_wan),
        step=50,
    )

    ping_range = st.sidebar.slider(
        "📐 建物面積範圍 (坪)：",
        min_value=0,
        max_value=max_ping_val,
        value=(0, max_ping_val),
        step=5,
    )

    # 執行資料過濾
    filtered_df = df[
        (df["total_price_wan"] >= price_range[0])
        & (df["total_price_wan"] <= price_range[1])
        & (df["building_ping"] >= ping_range[0])
        & (df["building_ping"] <= ping_range[1])
    ].copy()

    # 行政區過濾
    if selected_district != "全部區域":
        filtered_df = filtered_df[
            filtered_df["city_district"] == selected_district
        ]

    # 關鍵字過濾
    if search_term:
        filtered_df = filtered_df[
            filtered_df["address"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
            | filtered_df["building_type"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
        ]

    st.success(f"目前成功載入 {len(df)} 筆有效交易資料！")

    # ------------------ 📊 區域行情統計指標 ------------------
    district_label = (
        selected_district if selected_district != "全部區域" else "跨區總合"
    )
    st.subheader(f"📊 【{district_label}】行情統計")

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
            filtered_df["total_price_wan"].mean()
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

    # ------------------ 📈 圖表展示 ------------------
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        if selected_district == "全部區域":
            st.subheader("🏙️ 各行政區平均單價比較 (萬/坪)")
            district_stats = (
                filtered_df[filtered_df["unit_price_wan"] > 0]
                .groupby("city_district")["unit_price_wan"]
                .mean()
                .sort_values(ascending=False)
            )
            if not district_stats.empty:
                st.bar_chart(district_stats, color="#FF4B4B")
            else:
                st.info("尚無數據。")
        else:
            st.subheader(f"📈 【{selected_district}】單價區間分佈")
            if not valid_unit_price.empty:
                bins = [0, 15, 30, 45, 60, 75, 90, 100, 200]
                labels = [
                    "15萬以下",
                    "15-30萬",
                    "30-45萬",
                    "45-60萬",
                    "60-75萬",
                    "75-90萬",
                    "90-100萬",
                    "100萬以上",
                ]
                price_cut = pd.cut(
                    valid_unit_price, bins=bins, labels=labels, right=False
                )
                chart_data = price_cut.value_counts(sort=False).to_frame(
                    name="筆數"
                )
                st.bar_chart(chart_data, color="#FF4B4B")
            else:
                st.info("尚無單價資料。")

    with col_chart2:
        st.subheader("📌 坪數 vs 總價(萬元) 分佈圖")
        if not filtered_df.empty:
            chart_df = filtered_df[
                (filtered_df["building_ping"] > 0)
                & (filtered_df["total_price_wan"] > 0)
            ].copy()
            chart_df["總價(萬元)"] = chart_df["total_price_wan"]
            chart_df["坪數"] = chart_df["building_ping"]

            st.scatter_chart(
                chart_df, x="坪數", y="總價(萬元)", color="#1F77B4"
            )
        else:
            st.info("尚無資料可繪製圖表。")

    st.markdown("---")

    # 顯示詳細成交列表
    st.subheader(f"📋 【{district_label}】詳細成交列表（共 {len(filtered_df)} 筆）")
    st.dataframe(filtered_df, use_container_width=True)

else:
    st.warning("目前資料庫中沒有資料，請確認資料同步狀態。")