import streamlit as st
import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from src.backtest import run_ma_crossover_backtest, get_latest_signal_info

# 1. 페이지 레이아웃 및 테마 설정
st.set_page_config(
    page_title="QUANTMIND | 퀀트 백테스팅 & 스크리너",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS (KPI 카드, 헤더 스타일)
st.markdown("""
    <style>
    /* 메인 컨테이너 패딩 조절 */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        padding-left: 3rem;
        padding-right: 3rem;
    }
    
    /* 카드 스타일 컴포넌트 */
    .metric-card {
        background-color: #1e222d;
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid #2a2e39;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
    }
    .metric-title {
        font-size: 0.8rem;
        color: #848e9c;
        margin-bottom: 0.4rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .value-positive { color: #0ecb81; }
    .value-negative { color: #f6465d; }
    .value-neutral { color: #eaecef; }
    
    /* 그라디언트 헤더 및 타이틀 */
    .gradient-header {
        background: linear-gradient(90deg, #1f4068 0%, #162447 100%);
        padding: 1.2rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(22, 36, 71, 0.2);
    }
    .gradient-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
    }
    .gradient-header p {
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
        opacity: 0.85;
    }
    </style>
""", unsafe_allow_html=True)

# 2. 메인 헤더 영역
st.markdown("""
    <div class="gradient-header">
        <h1>QUANTMIND Backtest & Screener</h1>
        <p>이동평균 교차 전략 백테스팅과 다중 종목 성과 비교·순위 산출을 지원합니다.</p>
    </div>
""", unsafe_allow_html=True)

# 3. 사이드바 컨트롤러 구성
st.sidebar.markdown("### ⚙️ 공통 파라미터 설정")

# 모드 선택
mode = st.sidebar.radio(
    "🖥️ 분석 모드 선택",
    options=["🔍 다중 종목 스크리너 (Screener)", "📊 단일 종목 상세 분석 (Single)"],
    index=0
)

# 자산 및 그룹 템플릿 설정 (스크리너 전용)
if mode == "🔍 다중 종목 스크리너 (Screener)":
    group_type = st.sidebar.selectbox(
        "🗂️ 종목 그룹 선택",
        options=["🇺🇸 미국 빅테크 (Tech Giants)", "🪙 주요 암호화폐 (Crypto Major)", "🇰🇷 KOSPI IT/반도체", "✏️ 직접 티커 입력 (Custom)"]
    )
    
    if group_type == "🇺🇸 미국 빅테크 (Tech Giants)":
        ticker_input = "AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META"
    elif group_type == "🪙 주요 암호화폐 (Crypto Major)":
        ticker_input = "BTC-USD, ETH-USD, SOL-USD, DOGE-USD"
    elif group_type == "🇰🇷 KOSPI IT/반도체":
        ticker_input = "005930.KS, 000660.KS, 035420.KS, 035720.KS"
    else:
        ticker_input = st.sidebar.text_area("✍️ 티커 직접 입력 (콤마 구분)", value="AAPL, TSLA, BTC-USD")
else:
    # 단일 종목 모드
    ticker_input = st.sidebar.text_input("📊 분석 티커 입력 (Yahoo Finance)", value="AAPL", help="KOSPI 종목은 코드 뒤에 .KS를 붙여주세요 (예: 005930.KS)").upper()

# 날짜 설정
col_date1, col_date2 = st.sidebar.columns(2)
start_date = col_date1.date_input("시작일", datetime.date(2022, 1, 1))
end_date = col_date2.date_input("종료일", datetime.date.today())

# 이동평균 파라미터
fast_window = st.sidebar.slider("⏱️ 단기 이동평균선 (Fast MA)", min_value=2, max_value=100, value=10)
slow_window = st.sidebar.slider("⏱️ 장기 이동평균선 (Slow MA)", min_value=10, max_value=300, value=50)

# 자본 및 비용 파라미터
init_cash = st.sidebar.number_input("💵 초기 자본 ($)", min_value=100.0, value=10000.0, step=500.0)
fees_percent = st.sidebar.number_input("💸 거래 수수료 (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.01)
fees = fees_percent / 100.0

st.sidebar.markdown("---")
run_btn = st.sidebar.button("🚀 백테스트 실행", use_container_width=True)

# 4. 비즈니스 로직 실행
if run_btn:
    if fast_window >= slow_window:
        st.error("⚠️ 단기 이평선 기간은 장기 이평선 기간보다 작아야 합니다.")
    elif start_date >= end_date:
        st.error("⚠️ 시작일은 종료일보다 이전이어야 합니다.")
    else:
        # 공통 백테스트 시뮬레이션 구동
        with st.spinner("📊 금융 데이터를 다운로드하고 전략을 연산하는 중입니다..."):
            try:
                portfolio, close_df, fast_ma, slow_ma, entries, exits = run_ma_crossover_backtest(
                    ticker=ticker_input,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    fast_window=fast_window,
                    slow_window=slow_window,
                    init_cash=init_cash,
                    fees=fees
                )
                
                # ----------------------------------------------------
                # [모드 1] 다중 종목 스크리너 렌더링
                # ----------------------------------------------------
                if mode == "🔍 다중 종목 스크리너 (Screener)":
                    st.subheader("🏆 이동평균 교차 전략 기반 종목 스크리너")
                    
                    # 각 종목 성과 지표 산출
                    screener_data = []
                    valid_tickers = close_df.columns.tolist()
                    
                    for t in valid_tickers:
                        try:
                            stats = portfolio[t].stats()
                            sig = get_latest_signal_info(entries[t], exits[t])
                            
                            screener_data.append({
                                "종목명 (Ticker)": t,
                                "최근 시그널": sig,
                                "총 수익률 (%)": round(stats['Total Return [%]'], 2),
                                "최대 낙폭 (%)": round(stats['Max Drawdown [%]'], 2),
                                "샤프 지수 (Sharpe)": round(stats['Sharpe Ratio'], 3),
                                "승률 (%)": round(stats['Win Rate [%]'], 2) if not pd.isna(stats['Win Rate [%]']) else 0.0,
                                "총 거래 횟수": int(stats['Total Trades'])
                            })
                        except Exception as e:
                            st.warning(f"{t} 분석 중 오류 발생: {e}")
                            
                    screener_df = pd.DataFrame(screener_data)
                    
                    # 스크리너 정렬 옵션 제공
                    col_sort1, col_sort2 = st.columns([1, 3])
                    sort_key = col_sort1.selectbox(
                        "정렬 기준 선택", 
                        options=["샤프 지수 (Sharpe)", "총 수익률 (%)", "최대 낙폭 (%)", "승률 (%)"]
                    )
                    ascending_flag = True if sort_key == "최대 낙폭 (%)" else False
                    
                    sorted_screener_df = screener_df.sort_values(by=sort_key, ascending=ascending_flag).reset_index(drop=True)
                    
                    # 스크리너 테이블 출력 (컬러 매핑 적용)
                    st.dataframe(
                        sorted_screener_df.style.map(
                            lambda val: 'color: #0ecb81; font-weight: bold;' if '매수' in str(val) 
                            else 'color: #f6465d; font-weight: bold;' if '매도' in str(val) 
                            else '', 
                            subset=['최근 시그널']
                        ).map(
                            lambda val: 'color: #0ecb81; font-weight: bold;' if isinstance(val, (int, float)) and val > 0 
                            else 'color: #f6465d; font-weight: bold;' if isinstance(val, (int, float)) and val < 0 
                            else '', 
                            subset=['총 수익률 (%)']
                        ),
                        use_container_width=True
                    )
                    
                    # 비교 자산 수익률 차트 렌더링
                    st.subheader("📈 자산별 누적 수익률 비교 차트")
                    cum_returns = portfolio.cum_returns() * 100
                    
                    fig = go.Figure()
                    for t in valid_tickers:
                        fig.add_trace(go.Scatter(
                            x=cum_returns.index,
                            y=cum_returns[t],
                            mode='lines',
                            name=t,
                            line=dict(width=2)
                        ))
                        
                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="#161821",
                        plot_bgcolor="#161821",
                        xaxis_title="날짜 (Date)",
                        yaxis_title="누적 수익률 (%)",
                        height=500,
                        margin=dict(l=20, r=20, t=30, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                # ----------------------------------------------------
                # [모드 2] 단일 종목 상세 분석 렌더링
                # ----------------------------------------------------
                else:
                    t = close_df.columns[0]
                    stats = portfolio.stats()
                    
                    st.subheader(f"📊 {t} 상세 성과 지표 (KPIs)")
                    
                    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
                    
                    # 총 수익률 카드
                    total_return = stats['Total Return [%]']
                    tr_class = "value-positive" if total_return > 0 else "value-negative" if total_return < 0 else "value-neutral"
                    tr_sign = "+" if total_return > 0 else ""
                    kpi_col1.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-title">총 수익률 (Total Return)</div>
                            <div class="metric-value {tr_class}">{tr_sign}{total_return:.2f}%</div>
                            <div style="font-size: 0.8rem; color: #848e9c;">초기 자금 대비 누적 성과</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 최대 낙폭 카드
                    mdd = stats['Max Drawdown [%]']
                    mdd_class = "value-negative" if mdd > 10 else "value-neutral"
                    kpi_col2.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-title">최대 낙폭 (Max Drawdown)</div>
                            <div class="metric-value {mdd_class}">-{abs(mdd):.2f}%</div>
                            <div style="font-size: 0.8rem; color: #848e9c;">고점 대비 자산 하락 리스크</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 샤프 지수 카드
                    sharpe = stats['Sharpe Ratio']
                    sharpe_class = "value-positive" if sharpe >= 1.0 else "value-neutral" if sharpe >= 0 else "value-negative"
                    kpi_col3.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-title">샤프 지수 (Sharpe Ratio)</div>
                            <div class="metric-value {sharpe_class}">{sharpe:.2f}</div>
                            <div style="font-size: 0.8rem; color: #848e9c;">위험 조정 수익 지표</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 승률 카드
                    win_rate = stats['Win Rate [%]']
                    win_class = "value-positive" if win_rate >= 50 else "value-neutral"
                    kpi_col4.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-title">승률 및 포지션 상태</div>
                            <div class="metric-value {win_class}">{win_rate:.2f}%</div>
                            <div style="font-size: 0.8rem; color: #848e9c;">{get_latest_signal_info(entries[t], exits[t])}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # 성과 시각화 차트
                    st.subheader("📈 가격 차트, 이평선 및 매매 시그널")
                    fig = portfolio.plot(subplots=['cum_returns', 'drawdowns', 'trade_signals'])
                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="#161821",
                        plot_bgcolor="#161821",
                        height=700,
                        margin=dict(l=20, r=20, t=40, b=20)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 상세 통계 원본 표기
                    with st.expander("📝 전체 성과 세부 데이터 테이블 열기"):
                        st.dataframe(pd.DataFrame(stats).rename(columns={0: 'Value'}), use_container_width=True)
                        
            except Exception as e:
                st.exception(e)
                st.error(f"백테스팅 중 오류가 발생했습니다. 입력을 다시 확인해 주세요: {e}")
else:
    # 기본 메인 화면 랜딩 가이드
    st.info("👈 왼쪽 사이드바에서 [분석 모드] 및 파라미터를 설정한 후, **[백테스트 실행]** 버튼을 클릭해 주세요.")
    
    st.markdown("""
        ### 💡 한국 주식(KOSPI / KOSDAQ) 분석 팁
        현재 시스템은 실주가를 기준으로 분석을 수행하므로, 코스피/코스닥 종목도 직접 입력하여 분석할 수 있습니다.
        * **티커 입력 규칙**: 한국 종목은 주식 종목 코드(6자리 숫자) 뒤에 **`.KS`**(코스피) 또는 **`.KQ`**(코스닥)를 접미사로 붙여서 입력합니다.
          * 삼성전자 (코스피): `005930.KS`
          * SK하이닉스 (코스피): `000660.KS`
          * 네이버 (코스피): `035420.KS`
          * 카카오 (코스피): `035720.KS`
          * 에코프로비엠 (코스닥): `247540.KQ`
        * **다중 종목 스크리닝 기능**:
          * 사전 정의된 **KOSPI IT/반도체** 종목 그룹을 선택하여 즉시 백테스트 랭킹을 매길 수 있으며, `Custom` 모드에서 쉼표로 구분해 여러 한국 주식을 동시에 분석할 수도 있습니다.
    """)
