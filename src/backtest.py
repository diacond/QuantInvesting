import logging
import datetime
from typing import Tuple, List, Union
import pandas as pd
import yfinance as yf
import vectorbt as vbt

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_latest_signal_info(entries_series: pd.Series, exits_series: pd.Series) -> str:
    """
    개별 자산의 진입/청산 시그널 계열을 분석하여 가장 최근의 포지션 상태를 텍스트로 반환합니다.
    """
    entry_dates = entries_series[entries_series].index
    exit_dates = exits_series[exits_series].index
    
    if len(entry_dates) == 0 and len(exit_dates) == 0:
        return "관망 (No Signal)"
    
    if len(entry_dates) > 0 and len(exit_dates) == 0:
        return f"매수 진입 ({entry_dates[-1].strftime('%Y-%m-%d')})"
        
    if len(exit_dates) > 0 and len(entry_dates) == 0:
        return f"매도 청산 ({exit_dates[-1].strftime('%Y-%m-%d')})"
        
    last_entry = entry_dates[-1]
    last_exit = exit_dates[-1]
    
    if last_entry > last_exit:
        return f"매수 보유 ({last_entry.strftime('%Y-%m-%d')})"
    else:
        return f"현금 관망 ({last_exit.strftime('%Y-%m-%d')})"

def run_ma_crossover_backtest(
    ticker: Union[str, List[str]] = "AAPL",
    start_date: str = "2020-01-01",
    end_date: str = "2026-01-01",
    fast_window: int = 10,
    slow_window: int = 50,
    init_cash: float = 10000.0,
    fees: float = 0.001
) -> Tuple[vbt.Portfolio, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    다중 종목 또는 단일 종목의 이동평균선 교차 전략 백테스팅을 실행합니다.

    Parameters:
        ticker (Union[str, List[str]]): 콤마로 구분된 문자열 또는 티커 리스트 (예: 'AAPL, MSFT', ['AAPL', 'MSFT'])
        start_date (str): 백테스트 시작일 (YYYY-MM-DD)
        end_date (str): 백테스트 종료일 (YYYY-MM-DD)
        fast_window (int): 단기 이동평균선 기간
        slow_window (int): 장기 이동평균선 기간
        init_cash (float): 초기 자본금 (자산별 또는 공유 포트폴리오 기준)
        fees (float): 거래당 수수료 비율

    Returns:
        Tuple[vbt.Portfolio, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
            - portfolio: vectorbt Portfolio 객체 (다중 자산 칼럼 포함)
            - close: 종가 데이터 DataFrame
            - fast_ma: 단기 이동평균 DataFrame
            - slow_ma: 장기 이동평균 DataFrame
            - entries: 매수 시그널 DataFrame
            - exits: 매도 시그널 DataFrame
    """
    # 1. 입력 파라미터 파싱 및 검증
    if isinstance(ticker, str):
        tickers = [t.strip().upper() for t in ticker.split(",") if t.strip()]
    elif isinstance(ticker, list):
        tickers = [t.strip().upper() for t in ticker if t.strip()]
    else:
        raise ValueError("ticker는 콤마로 구분된 문자열이거나 리스트 형태여야 합니다.")

    if not tickers:
        raise ValueError("유효한 티커명이 제공되지 않았습니다.")

    if fast_window <= 0 or slow_window <= 0:
        raise ValueError("이동평균선 기간은 양의 정수여야 합니다.")
        
    if fast_window >= slow_window:
        raise ValueError(f"단기 이동평균선 기간({fast_window})은 장기 이동평균선 기간({slow_window})보다 작아야 합니다.")
        
    if init_cash <= 0:
        raise ValueError("초기 자본금은 0보다 커야 합니다.")
        
    if not (0 <= fees <= 1):
        raise ValueError("수수료 비율은 0과 1 사이여야 합니다.")

    try:
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        if start_dt >= end_dt:
            raise ValueError("시작일은 종료일보다 이전이어야 합니다.")
    except ValueError as e:
        if "strptime" in str(e):
            raise ValueError(f"날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식이어야 합니다. 입력값: start={start_date}, end={end_date}")
        raise e

    # 2. 데이터 다운로드 실행
    logger.info(f"yfinance 데이터 다운로드 중 (대상: {tickers}) | 기간: {start_date} ~ {end_date}")
    
    try:
        if len(tickers) == 1:
            df = yf.download(tickers[0], start=start_date, end=end_date, progress=False)
            if df.empty:
                raise ValueError(f"'{tickers[0]}' 종목의 데이터를 다운로드할 수 없습니다.")
            # 1개 종목인 경우 DataFrame의 컬럼명을 티커로 지정하여 일관성 유지
            close_df = df['Close'].to_frame(name=tickers[0])
        else:
            df = yf.download(tickers, start=start_date, end=end_date, progress=False)
            if df.empty:
                raise ValueError("제공된 티커들의 데이터를 전혀 다운로드할 수 없습니다.")
            
            # yfinance 다중 종목 MultiIndex 컬럼 정규화 처리
            if isinstance(df.columns, pd.MultiIndex):
                if 'Close' in df.columns.levels[0]:
                    close_df = df['Close']
                else:
                    close_df = df.xs('Close', axis=1, level=0)
            else:
                close_df = df['Close']
    except Exception as e:
        logger.error(f"yfinance 데이터 다운로드 중 예외 발생: {e}")
        raise RuntimeError(f"데이터 수집에 실패했습니다: {e}")

    # 결측치 열 및 유효 데이터 수 검증
    close_df = close_df.dropna(how='all')
    
    # 일부 종목이 다운로드 실패하여 누락되었을 때의 대처
    valid_tickers = []
    for t in tickers:
        if t in close_df.columns:
            # 전체가 NaN인 열 제외
            if close_df[t].isna().all():
                close_df = close_df.drop(columns=[t])
            else:
                valid_tickers.append(t)
                
    if not valid_tickers:
        raise ValueError("분석에 활용할 수 있는 유효한 종목 데이터가 존재하지 않습니다.")

    # 3. 데이터 길이 검증
    # 유효한 최소 데이터 개수 기준: slow_window
    min_data_len = close_df.count().min()
    if min_data_len < slow_window:
        raise ValueError(f"데이터 개수(최소 {min_data_len}개)가 장기 이동평균선 기간({slow_window})보다 적어 분석을 진행할 수 없습니다.")

    # 4. vectorbt를 활용한 이동평균선 및 시그널 계산
    logger.info("이동평균선 및 시그널 계산 중...")
    try:
        fast_ma = vbt.MA.run(close_df, fast_window)
        slow_ma = vbt.MA.run(close_df, slow_window)
        
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)
        
        # 컬럼을 단일 레벨(티커명)로 단순화하여 vectorbt의 파라미터 멀티인덱스 복잡성 해소
        if isinstance(entries.columns, pd.MultiIndex):
            entries.columns = close_df.columns
            exits.columns = close_df.columns
            
        fast_ma_df = fast_ma.ma
        slow_ma_df = slow_ma.ma
        if isinstance(fast_ma_df.columns, pd.MultiIndex):
            fast_ma_df.columns = close_df.columns
            slow_ma_df.columns = close_df.columns
    except Exception as e:
        logger.error(f"이동평균/시그널 계산 중 예외 발생: {e}")
        raise RuntimeError(f"전략 계산에 실패했습니다: {e}")

    # 5. vectorbt 포트폴리오 시뮬레이션
    logger.info("vectorbt 포트폴리오 시뮬레이션 실행 중...")
    try:
        portfolio = vbt.Portfolio.from_signals(
            close=close_df,
            entries=entries,
            exits=exits,
            init_cash=init_cash,
            fees=fees,
            freq='D',
            cash_sharing=False # 자산별 독립 예산으로 각각 실행하도록 설정
        )
    except Exception as e:
        logger.error(f"vectorbt 시뮬레이션 중 예외 발생: {e}")
        raise RuntimeError(f"백테스팅 시뮬레이션에 실패했습니다: {e}")

    logger.info("백테스팅 완료.")
    return portfolio, close_df, fast_ma_df, slow_ma_df, entries, exits

if __name__ == "__main__":
    # 다중 종목 로컬 테스트 실행
    try:
        portfolio, close, fast, slow, entries, exits = run_ma_crossover_backtest(
            ticker="AAPL, MSFT, TSLA",
            start_date="2022-01-01",
            end_date="2026-01-01",
            fast_window=10,
            slow_window=50
        )
        for t in ["AAPL", "MSFT", "TSLA"]:
            if t in close.columns:
                print(f"\n=== {t} 성과 요약 ===")
                stats = portfolio[t].stats()
                print(f"Total Return: {stats['Total Return [%]']:.2f}% | Sharpe: {stats['Sharpe Ratio']:.3f} | MDD: {stats['Max Drawdown [%]']:.2f}%")
                
                # 시그널 요약 테스트
                sig = get_latest_signal_info(entries[t], exits[t])
                print(f"Latest Signal: {sig}")
                
    except Exception as e:
        logger.exception(f"실행 중 오류 발생: {e}")
