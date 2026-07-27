# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Dict, Optional, Union, Tuple

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,  # @informative decorator
    # Hyperopt Parameters
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    # timeframe helpers
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    # Strategy helper functions
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
    AnnotationType,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
from technical import qtpylib
import pandas_ta as pdta


class DayStrategy(IStrategy):
    """
    BTC,ETH,SOL 永续合约日内交易策略
    1）技术分析
    2）下单
    3）仓位管理
    4）止损
    - 主周期: 5m
    - 辅助周期: 1m, 30m
    - 跨交易对分析: BTC/ETH/SOL 互相作为辅助

    This is a strategy template to get you started.
    More information in https://www.freqtrade.io/en/stable/strategy-customization/

    You can:
        :return: a Dataframe with all mandatory indicators for the strategies
    - Rename the class name (Do not forget to update class_name)
    - Add any methods you want to build your strategy
    - Add any lib you need to build your strategy

    You must keep:
    - the lib in the section "Do not remove these libs"
    - the methods: populate_indicators, populate_entry_trend, populate_exit_trend
    You should keep:
    - timeframe, minimal_roi, stoploss, trailing_*
    """
    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    # Optimal timeframe for the strategy.
    timeframe = "5m"

    # Can this strategy go short?
    can_short: bool = True

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.10

    # Trailing stoploss
    trailing_stop = False
    # trailing_only_offset_is_reached = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.0  # Disabled / not configured

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 100

    # Strategy parameters
    buy_rsi = IntParameter(10, 40, default=30, space="buy")
    sell_rsi = IntParameter(60, 90, default=70, space="sell")# Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False
    }

    # Optional order time in force.
    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC"
    }

    # 蜡烛类型（期货）
    candle_type_def = "futures"

    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            "main_plot": {
                "tema": {},
                "sar": {"color": "white"},
            },
            "subplots": {
                # Subplots - each dict defines one additional plot
                "MACD": {
                    "macd": {"color": "blue"},
                    "macdsignal": {"color": "orange"},
                },
                "RSI": {
                    "rsi": {"color": "red"},
                }
            }
        }

    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        These pair/interval combinations are non-tradeable, unless they are part
        of the whitelist as well.
        For more information, please consult the documentation
        :return: List of tuples in the format (pair, interval)
            Sample: return [("ETH/USDT", "5m"),
                            ("BTC/USDT", "15m"),
                            ]
        """
        return []

    def _calculate_zigzag_pandas_ta(self, dataframe: DataFrame) -> DataFrame:
        """
        使用 pandas-ta 中的 zigzag 方法计算 ZigZag 指标
        如果 pandas_ta 不可用，则回退到自定义实现

        :param dataframe: 包含 high, low, close 的 DataFrame
        :return: 添加了 ZigZag 指标的 DataFrame
        """
        df = dataframe.copy()

        try:
            # 使用 pandas_ta 的 zigzag 方法
            # 注意：必须使用关键字参数传递所有参数，避免自动检测列时的冲突
            zigzag_result = df.ta.zigzag(
                high=df["high"], 
                low=df["low"], 
                close=df["close"], 
                # legs=10, 
                # deviation=5, 
                # backtest=True, 
                # offset=0
            )

            # 将 zigzag 结果合并到原始 dataframe
            df = df.join(zigzag_result)

        except Exception as e:
            # 如果 pandas_ta 不可用或出错，回退到自定义实现
            self.log.warning(f"pandas_ta zigzag failed: {e}, falling back to custom implementation")
            #df = self._calculate_zigzag(df)

        return df

    def _calculate_zigzag(self, dataframe: DataFrame) -> DataFrame:
        """
        自定义 ZigZag 指标计算函数
        识别价格的高点和低点，用于趋势反转分析
        
        :param dataframe: 包含 high, low, close 的 DataFrame
        :param deviation: 最小波动百分比阈值（默认 0.5%）
        :param min_legs: 最小腿数（默认 3）
        :return: 添加了 ZigZag 指标的 DataFrame
        """
        deviation = 0.5  # 0.5% 波动阈值
        min_legs = 3     # 最小腿数
        
        df = dataframe.copy()
        df["zigzag_high"] = np.nan
        df["zigzag_low"] = np.nan
        df["zigzag_dir"] = 0  # 1=上升, -1=下降, 0=未确定
        df["zigzag_pivot"] = 0  # 1=高点, -1=低点, 0=普通
        
        if len(df) < min_legs * 2:
            return df
        
        # 初始化变量
        trend_direction = 0  # 0=未确定, 1=上升, -1=下降
        pivot_index = 0
        pivot_price = df.iloc[0]["close"]
        
        for i in range(1, len(df)):
            current_high = df.iloc[i]["high"]
            current_low = df.iloc[i]["low"]
            
            # 计算价格变化百分比
            change_from_pivot = abs((current_high - pivot_price) / pivot_price * 100) if pivot_price != 0 else 0
            change_from_pivot_low = abs((current_low - pivot_price) / pivot_price * 100) if pivot_price != 0 else 0
            
            if trend_direction == 0:
                # 初始状态，确定第一个趋势方向
                if change_from_pivot >= deviation:
                    trend_direction = 1  # 上升趋势
                    pivot_index = i
                    pivot_price = current_high
                    df.loc[df.index[i], "zigzag_high"] = current_high
                    df.loc[df.index[i], "zigzag_pivot"] = 1
                    df.loc[df.index[i], "zigzag_dir"] = 1
                elif change_from_pivot_low >= deviation:
                    trend_direction = -1  # 下降趋势
                    pivot_index = i
                    pivot_price = current_low
                    df.loc[df.index[i], "zigzag_low"] = current_low
                    df.loc[df.index[i], "zigzag_pivot"] = -1
                    df.loc[df.index[i], "zigzag_dir"] = -1
            
            elif trend_direction == 1:
                # 当前是上升趋势，寻找更高的高点或反转
                if current_high > pivot_price:
                    # 更新高点
                    df.loc[df.index[pivot_index], "zigzag_high"] = np.nan
                    df.loc[df.index[pivot_index], "zigzag_pivot"] = 0
                    pivot_index = i
                    pivot_price = current_high
                    df.loc[df.index[i], "zigzag_high"] = current_high
                    df.loc[df.index[i], "zigzag_pivot"] = 1
                    df.loc[df.index[i], "zigzag_dir"] = 1
                elif (pivot_price - current_low) / pivot_price * 100 >= deviation:
                    # 反转到下降趋势
                    trend_direction = -1
                    pivot_index = i
                    pivot_price = current_low
                    df.loc[df.index[i], "zigzag_low"] = current_low
                    df.loc[df.index[i], "zigzag_pivot"] = -1
                    df.loc[df.index[i], "zigzag_dir"] = -1
            
            elif trend_direction == -1:
                # 当前是下降趋势，寻找更低的低点或反转
                if current_low < pivot_price:
                    # 更新低点
                    df.loc[df.index[pivot_index], "zigzag_low"] = np.nan
                    df.loc[df.index[pivot_index], "zigzag_pivot"] = 0
                    pivot_index = i
                    pivot_price = current_low
                    df.loc[df.index[i], "zigzag_low"] = current_low
                    df.loc[df.index[i], "zigzag_pivot"] = -1
                    df.loc[df.index[i], "zigzag_dir"] = -1
                elif (current_high - pivot_price) / pivot_price * 100 >= deviation:
                    # 反转到上升趋势
                    trend_direction = 1
                    pivot_index = i
                    pivot_price = current_high
                    df.loc[df.index[i], "zigzag_high"] = current_high
                    df.loc[df.index[i], "zigzag_pivot"] = 1
                    df.loc[df.index[i], "zigzag_dir"] = 1
        
        # 向前填充高点和低点值
        df["zigzag_high_ffill"] = df["zigzag_high"].ffill()
        df["zigzag_low_ffill"] = df["zigzag_low"].ffill()
        
        
        
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """
        # ZigZag 指标 - 识别高点和低点
        dataframe = self._calculate_zigzag(dataframe)
        dataframe = self._calculate_zigzag_pandas_ta(dataframe)
        





        # Momentum Indicators
        # ------------------------------------

        # ADX
        dataframe["adx"] = ta.ADX(dataframe)

        # # Plus Directional Indicator / Movement
        # dataframe["plus_dm"] = ta.PLUS_DM(dataframe)
        # dataframe["plus_di"] = ta.PLUS_DI(dataframe)

        # # Minus Directional Indicator / Movement
        # dataframe["minus_dm"] = ta.MINUS_DM(dataframe)
        # dataframe["minus_di"] = ta.MINUS_DI(dataframe)

        # # Aroon, Aroon Oscillator
        # aroon = ta.AROON(dataframe)
        # dataframe["aroonup"] = aroon["aroonup"]
        # dataframe["aroondown"] = aroon["aroondown"]
        # dataframe["aroonosc"] = ta.AROONOSC(dataframe)

        # # Awesome Oscillator
        # dataframe["ao"] = qtpylib.awesome_oscillator(dataframe)

        # # Keltner Channel
        # keltner = qtpylib.keltner_channel(dataframe)
        # dataframe["kc_upperband"] = keltner["upper"]
        # dataframe["kc_lowerband"] = keltner["lower"]
        # dataframe["kc_middleband"] = keltner["mid"]
        # dataframe["kc_percent"] = (
        #     (dataframe["close"] - dataframe["kc_lowerband"]) /
        #     (dataframe["kc_upperband"] - dataframe["kc_lowerband"])
        # )
        # dataframe["kc_width"] = (
        #     (dataframe["kc_upperband"] - dataframe["kc_lowerband"]) / dataframe["kc_middleband"]
        # )

        # # Ultimate Oscillator
        # dataframe["uo"] = ta.ULTOSC(dataframe)

        # # Commodity Channel Index: values [Oversold:-100, Overbought:100]
        # dataframe["cci"] = ta.CCI(dataframe)

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe)

        # # Inverse Fisher transform on RSI: values [-1.0, 1.0] (https://goo.gl/2JGGoy)
        # rsi = 0.1 * (dataframe["rsi"] - 50)
        # dataframe["fisher_rsi"] = (np.exp(2 * rsi) - 1) / (np.exp(2 * rsi) + 1)

        # # Inverse Fisher transform on RSI normalized: values [0.0, 100.0] (https://goo.gl/2JGGoy)
        # dataframe["fisher_rsi_norma"] = 50 * (dataframe["fisher_rsi"] + 1)

        # # Stochastic Slow
        # stoch = ta.STOCH(dataframe)
        # dataframe["slowd"] = stoch["slowd"]
        # dataframe["slowk"] = stoch["slowk"]

        # Stochastic Fast
        stoch_fast = ta.STOCHF(dataframe)
        dataframe["fastd"] = stoch_fast["fastd"]
        dataframe["fastk"] = stoch_fast["fastk"]

        # # Stochastic RSI
        # Please read https://github.com/freqtrade/freqtrade/issues/2961 before using this.
        # STOCHRSI is NOT aligned with tradingview, which may result in non-expected results.
        # stoch_rsi = ta.STOCHRSI(dataframe)
        # dataframe["fastd_rsi"] = stoch_rsi["fastd"]
        # dataframe["fastk_rsi"] = stoch_rsi["fastk"]

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # MFI
        dataframe["mfi"] = ta.MFI(dataframe)

        # # ROC
        # dataframe["roc"] = ta.ROC(dataframe)

        # Overlap Studies
        # ------------------------------------

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_percent"] = (
            (dataframe["close"] - dataframe["bb_lowerband"]) /
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
        )
        dataframe["bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]
        )

        # Bollinger Bands - Weighted (EMA based instead of SMA)
        # weighted_bollinger = qtpylib.weighted_bollinger_bands(
        #     qtpylib.typical_price(dataframe), window=20, stds=2
        # )
        # dataframe["wbb_upperband"] = weighted_bollinger["upper"]
        # dataframe["wbb_lowerband"] = weighted_bollinger["lower"]
        # dataframe["wbb_middleband"] = weighted_bollinger["mid"]
        # dataframe["wbb_percent"] = (
        #     (dataframe["close"] - dataframe["wbb_lowerband"]) /
        #     (dataframe["wbb_upperband"] - dataframe["wbb_lowerband"])
        # )
        # dataframe["wbb_width"] = (
        #     (dataframe["wbb_upperband"] - dataframe["wbb_lowerband"]) / dataframe["wbb_middleband"]
        # )

        # # EMA - Exponential Moving Average
        # dataframe["ema3"] = ta.EMA(dataframe, timeperiod=3)
        # dataframe["ema5"] = ta.EMA(dataframe, timeperiod=5)
        # dataframe["ema10"] = ta.EMA(dataframe, timeperiod=10)
        # dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        # dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        # dataframe["ema100"] = ta.EMA(dataframe, timeperiod=100)

        # # SMA - Simple Moving Average
        # dataframe["sma3"] = ta.SMA(dataframe, timeperiod=3)
        # dataframe["sma5"] = ta.SMA(dataframe, timeperiod=5)
        # dataframe["sma10"] = ta.SMA(dataframe, timeperiod=10)
        # dataframe["sma21"] = ta.SMA(dataframe, timeperiod=21)
        # dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        # dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)

        # Parabolic SAR
        dataframe["sar"] = ta.SAR(dataframe)

        # TEMA - Triple Exponential Moving Average
        dataframe["tema"] = ta.TEMA(dataframe, timeperiod=9)

        # Cycle Indicator
        # ------------------------------------
        # Hilbert Transform Indicator - SineWave
        hilbert = ta.HT_SINE(dataframe)
        dataframe["htsine"] = hilbert["sine"]
        dataframe["htleadsine"] = hilbert["leadsine"]

        # Pattern Recognition - Bullish candlestick patterns
        # ------------------------------------
        # # Hammer: values [0, 100]
        # dataframe["CDLHAMMER"] = ta.CDLHAMMER(dataframe)
        # # Inverted Hammer: values [0, 100]
        # dataframe["CDLINVERTEDHAMMER"] = ta.CDLINVERTEDHAMMER(dataframe)
        # # Dragonfly Doji: values [0, 100]
        # dataframe["CDLDRAGONFLYDOJI"] = ta.CDLDRAGONFLYDOJI(dataframe)
        # # Piercing Line: values [0, 100]
        # dataframe["CDLPIERCING"] = ta.CDLPIERCING(dataframe) # values [0, 100]
        # # Morningstar: values [0, 100]
        # dataframe["CDLMORNINGSTAR"] = ta.CDLMORNINGSTAR(dataframe) # values [0, 100]
        # # Three White Soldiers: values [0, 100]
        # dataframe["CDL3WHITESOLDIERS"] = ta.CDL3WHITESOLDIERS(dataframe) # values [0, 100]

        # Pattern Recognition - Bearish candlestick patterns
        # ------------------------------------
        # # Hanging Man: values [0, 100]
        # dataframe["CDLHANGINGMAN"] = ta.CDLHANGINGMAN(dataframe)
        # # Shooting Star: values [0, 100]
        # dataframe["CDLSHOOTINGSTAR"] = ta.CDLSHOOTINGSTAR(dataframe)
        # # Gravestone Doji: values [0, 100]
        # dataframe["CDLGRAVESTONEDOJI"] = ta.CDLGRAVESTONEDOJI(dataframe)
        # # Dark Cloud Cover: values [0, 100]
        # dataframe["CDLDARKCLOUDCOVER"] = ta.CDLDARKCLOUDCOVER(dataframe)
        # # Evening Doji Star: values [0, 100]
        # dataframe["CDLEVENINGDOJISTAR"] = ta.CDLEVENINGDOJISTAR(dataframe)
        # # Evening Star: values [0, 100]
        # dataframe["CDLEVENINGSTAR"] = ta.CDLEVENINGSTAR(dataframe)

        # Pattern Recognition - Bullish/Bearish candlestick patterns
        # ------------------------------------
        # # Three Line Strike: values [0, -100, 100]
        # dataframe["CDL3LINESTRIKE"] = ta.CDL3LINESTRIKE(dataframe)
        # # Spinning Top: values [0, -100, 100]
        # dataframe["CDLSPINNINGTOP"] = ta.CDLSPINNINGTOP(dataframe) # values [0, -100, 100]
        # # Engulfing: values [0, -100, 100]
        # dataframe["CDLENGULFING"] = ta.CDLENGULFING(dataframe) # values [0, -100, 100]
        # # Harami: values [0, -100, 100]
        # dataframe["CDLHARAMI"] = ta.CDLHARAMI(dataframe) # values [0, -100, 100]
        # # Three Outside Up/Down: values [0, -100, 100]
        # dataframe["CDL3OUTSIDE"] = ta.CDL3OUTSIDE(dataframe) # values [0, -100, 100]
        # # Three Inside Up/Down: values [0, -100, 100]
        # dataframe["CDL3INSIDE"] = ta.CDL3INSIDE(dataframe) # values [0, -100, 100]

        # # Chart type
        # # ------------------------------------
        # # Heikin Ashi Strategy
        # heikinashi = qtpylib.heikinashi(dataframe)
        # dataframe["ha_open"] = heikinashi["open"]
        # dataframe["ha_close"] = heikinashi["close"]
        # dataframe["ha_high"] = heikinashi["high"]
        # dataframe["ha_low"] = heikinashi["low"]

        # Retrieve best bid and best ask from the orderbook
        # ------------------------------------
        """
        # first check if dataprovider is available
        if self.dp:
            if self.dp.runmode.value in ("live", "dry_run"):
                ob = self.dp.orderbook(metadata["pair"], 1)
                dataframe["best_bid"] = ob["bids"][0][0]
                dataframe["best_ask"] = ob["asks"][0][0]
        """

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        """
        入场信号 - 此策略暂不生成入场信号
        仅计算指标用于分析
        """
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0

        # dataframe.loc[
        #     (
        #         (qtpylib.crossed_above(dataframe["rsi"], self.buy_rsi.value)) &  # Signal: RSI crosses above buy_rsi
        #         (dataframe["tema"] <= dataframe["bb_middleband"]) &  # Guard: tema below BB middle
        #         (dataframe["tema"] > dataframe["tema"].shift(1)) &  # Guard: tema is raising
        #         (dataframe["volume"] > 0)  # Make sure Volume is not 0
        #     ),
        #     "enter_long"] = 1
        # Uncomment to use shorts (Only used in futures/margin mode. Check the documentation for more info)
        """
        dataframe.loc[
            (
                (qtpylib.crossed_above(dataframe["rsi"], self.sell_rsi.value)) &  # Signal: RSI crosses above sell_rsi
                (dataframe["tema"] > dataframe["bb_middleband"]) &  # Guard: tema above BB middle
                (dataframe["tema"] < dataframe["tema"].shift(1)) &  # Guard: tema is falling
                (dataframe['volume'] > 0)  # Make sure Volume is not 0
            ),
            'enter_short'] = 1
        """

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """
        """
        出场信号 - 此策略暂不生成出场信号
        仅计算指标用于分析
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        # dataframe.loc[
        #     (
        #         (qtpylib.crossed_above(dataframe["rsi"], self.sell_rsi.value)) &  # Signal: RSI crosses above sell_rsi
        #         (dataframe["tema"] > dataframe["bb_middleband"]) &  # Guard: tema above BB middle
        #         (dataframe["tema"] < dataframe["tema"].shift(1)) &  # Guard: tema is falling
        #         (dataframe["volume"] > 0)  # Make sure Volume is not 0
        #     ),
        #     "exit_long"] = 1
        # Uncomment to use shorts (Only used in futures/margin mode. Check the documentation for more info)
        """
        dataframe.loc[
            (
                (qtpylib.crossed_above(dataframe["rsi"], self.buy_rsi.value)) &  # Signal: RSI crosses above buy_rsi
                (dataframe["tema"] <= dataframe["bb_middleband"]) &  # Guard: tema below BB middle
                (dataframe["tema"] > dataframe["tema"].shift(1)) &  # Guard: tema is raising
                (dataframe['volume'] > 0)  # Make sure Volume is not 0
            ),
            'exit_short'] = 1
        """
        return dataframe