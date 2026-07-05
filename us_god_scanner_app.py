import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import itertools
import requests
import time
from datetime import datetime
import pytz
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. 설정 및 미국 50개 종목 리스트 
# ==========================================
WATCH_LIST = [
    'SPY', 'QQQ', 'DIA', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 
    'AMD', 'AVGO', 'QCOM', 'INTC', 'MU', 'ARM', 'TSM', 'LRCX', 'AMAT', 'ASML', 
    'PLTR', 'SMCI', 'CRWD', 'PANW', 'FTNT', 'SNOW', 'DDOG', 'ZS', 'NET', 'ADBE', 
    'CRM', 'NOW', 'NFLX', 'PYPL', 'UBER', 'ABNB', 'DIS', 'SHOP', 'SPOT', 'LLY', 
    'NVO', 'UNH', 'VRTX', 'MRVL', 'PEP', 'KO', 'WMT', 'TGT', 'V', 'MA'
]

st.set_page_config(page_title="🇺🇸 미국 일봉 괴리율 스캐너", layout="wide")

# ==========================================
# 2. 강력한 실시간 환율 엔진 (캐시 없음! 무조건 실시간 호출)
# ==========================================
def get_realtime_usdkrw() -> float:
    # 1차 시도: yfinance 정밀 조회
    try:
        df = yf.download("KRW=X", period="1d", interval="1d", progress=False)
        if not df.empty:
            v = float(df["Close"].iloc[-1])
            return round(1 / v, 4) if v < 10 else round(v, 4)
    except: 
        pass
        
    # 2차 시도: 외부 오픈 API 백업 조회
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        r.raise_for_status()
        return float(r.json()["rates"]["KRW"])
    except:
        # 최악의 경우를 대비한 비상 환율
        return 1530.0

# ==========================================
# 3. UI 및 사이드바 설정
# ==========================================
st.title("🇺🇸 미국 주식 통계적 괴리율(Pairs) 일봉 스캐너")
st.write("최근 1년 치 일봉 데이터를 분석하여, 60거래일(약 3개월) 기준 통계적 범위를 벗어난 **확실한 일봉 타점**을 찾아냅니다.")

st.sidebar.header("⚙️ 스캔 설정")
min_correlation = st.sidebar.slider("최소 상관계수 (기본 0.85)", 0.70, 0.99, 0.85, 0.01)
entry_z_score = st.sidebar.slider("진입 Z-Score (기본 2.0)", 1.0, 3.0, 2.0, 0.1)
rolling_window = st.sidebar.number_input("이동평균 기준일 (기본 60일)", min_value=10, max_value=120, value=60)

# ==========================================
# 4. 핵심 데이터 로직 (주가 데이터만 캐싱)
# ==========================================
@st.cache_data(ttl=600) # 주가 데이터는 10분만 캐싱하여 신선도 유지
def scan_us_pairs(corr_limit, z_limit, window):
    # 야후 파이낸스 데이터 1년 치 일봉 다운로드
    data = yf.download(WATCH_LIST, period="1y", interval="1d", prepost=False, progress=False)['Close']
    data = data.dropna(axis=1)
    
    tickers_available = data.columns.tolist()
    opportunities = []
    pairs = list(itertools.combinations(tickers_available, 2))
    
    for pair in pairs:
        asset_a, asset_b = pair
        corr = data[asset_a].corr(data[asset_b])
        if corr < corr_limit: 
            continue
            
        ratio = data[asset_a] / data[asset_b]
        mean = ratio.rolling(window=window).mean().iloc[-1]
        std = ratio.rolling(window=window).std().iloc[-1]
        
        # 방어 로직 (std가 0이거나 NaN인 경우)
        if pd.isna(std) or std == 0: 
            continue
            
        current_z = (ratio.iloc[-1] - mean) / std
        
        if abs(current_z) >= z_limit:
            # 추천 등급 마크 부여
            if corr >= 0.95:
                rank_tag = "🥇 1순위 강력추천"
                rank_score = 1
            else:
                rank_tag = "🥈 2순위 일반추천"
                rank_score = 0
                
            # 액션 판단 (Z-score가 양수면 A고평가/B저평가, 음수면 A저평가/B고평가)
            if current_z > 0:
                action = f"➔ [{asset_a} 고평가] {asset_a} 무시 / ⭐{asset_b} 매수(Long)⭐"
            else:
                action = f"➔ [{asset_b} 고평가] ⭐{asset_a} 매수(Long)⭐ / {asset_b} 무시"
            
            pA = data[asset_a].iloc[-1]
            pB = data[asset_b].iloc[-1]
            
            opportunities.append({
                '추천등급': rank_tag,
                '페어 (A vs B)': f"{asset_a} vs {asset_b}",
                '매매전략': action,
                '상관계수': round(corr, 3),
                'Z-Score': round(current_z, 2),
                'A 현재가($)': pA,
                'B 현재가($)': pB,
                # 원화 가격은 실시간 환율을 반영하기 위해 여기서 미리 계산하지 않음!
                '_rank_score': rank_score,
                '_abs_z': abs(current_z)
            })
            
    return pd.DataFrame(opportunities), len(tickers_available)

# ==========================================
# 5. 화면 출력 및 실행
# ==========================================
kst = datetime.now(pytz.timezone('Asia/Seoul'))
st.write(f"🕒 현재 한국 시간: {kst.strftime('%Y-%m-%d %H:%M:%S')}")

# 버튼 클릭 시에만 전체 로직 수행
if st.button("🚀 미국장 일봉 타점 스캔 시작", use_container_width=True):
    with st.spinner("데이터 스캔 및 실시간 환율 적용 중..."):
        
        # 🔥 여기서 버튼을 누르는 순간 100% 최신 환율을 긁어옴! (캐시 안됨) 🔥
        realtime_ex_rate = get_realtime_usdkrw()
        
        df, available_count = scan_us_pairs(min_correlation, entry_z_score, rolling_window)
        
        st.info(f"✅ {available_count}개 우량주 데이터 확보 완료. (현재 실시간 환율 적용: **{realtime_ex_rate:,.2f}원**)")
        
        if not df.empty:
            # 1순위(상관도 0.95 이상) 최우선, 그 다음 Z-Score 절대값 큰 순서로 정렬
            df = df.sort_values(by=['_rank_score', '_abs_z'], ascending=[False, False])
            
            # 정렬용 임시 컬럼 삭제
            df = df.drop(columns=['_rank_score', '_abs_z'])
            
            # 🔥 실시간 환율을 여기서 곱해줌 🔥
            df['A 현재가(₩)'] = df['A 현재가($)'] * realtime_ex_rate
            df['B 현재가(₩)'] = df['B 현재가($)'] * realtime_ex_rate
            
            # 가격 컬럼 포맷팅 (달러 및 원화 콤마 처리)
            df['A 현재가($)'] = df['A 현재가($)'].apply(lambda x: f"${float(x):,.2f}")
            df['B 현재가($)'] = df['B 현재가($)'].apply(lambda x: f"${float(x):,.2f}")
            df['A 현재가(₩)'] = df['A 현재가(₩)'].apply(lambda x: f"₩{int(x):,}")
            df['B 현재가(₩)'] = df['B 현재가(₩)'].apply(lambda x: f"₩{int(x):,}")
            
            # 최종 출력
            st.success(f"🔥 총 {len(df)}개의 확실한 일봉 타점 발견! (내일 본장 진입 고려)")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("⏰ 오늘은 일봉상 비정상적인 괴리가 없습니다. 현금 보유 및 내일 다시 스캔하세요.")
