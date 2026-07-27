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

import logging
logger = logging.getLogger(__name__)

class MyTemplateAdvanced(IStrategy):
    """
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
    can_short: bool = False

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
    startup_candle_count: int = 30

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

    # 策略参数定义
    trade_direction = IntParameter(
        0, 1, default=0, space="optimize",
        help="交易方向: 0=做多, 1=做空"
    )
    initial_price = DecimalParameter(
        0.0, 70000.0, decimals=2, default=70000.0, space="optimize",
        help="首次开仓价格"
    )
    price_interval = DecimalParameter(
        0.0, 200.0, decimals=2, default=100.0, space="optimize",
        help="每次开仓的价格间隔"
    )
    max_trades = IntParameter(
        1, 10, default=5, space="optimize",
        help="最大开仓次数"
    )

    # 启用仓位调整（允许加仓）
    position_adjustment_enable = True
    max_entry_position_adjustment = 10

    def __init__(self, config: dict):
        super().__init__(config)
        self.trade_states = {}

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

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """指标计算（此处可扩展）"""
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        首次开仓信号生成
        """
        pair = metadata['pair']
        
        # 检查是否有开放交易，如果没有则重置状态
        open_trades = Trade.get_open_trades()
        has_open_trade = any(t.pair == pair for t in open_trades)
        
        if pair not in self.trade_states or not has_open_trade:
            self.trade_states[pair] = {
                'count': 0,
                'last_price': self.initial_price.value
            }
            
        state = self.trade_states[pair]
        direction = self.trade_direction.value
        
        # 防止重复开仓
        if state['count'] >= self.max_trades.value:
            return dataframe
            
        # 做多逻辑：价格首次下跌触及 initial_price
        if direction == 0:
            dataframe.loc[
                (dataframe['close'] <= state['last_price']) &
                (dataframe['volume'] > 0),
                'enter_long'
            ] = 1
            dataframe.loc[
                (dataframe['close'] <= state['last_price']) &
                (dataframe['volume'] > 0),
                'enter_tag'
            ] = 'initial_long'
            
        # 做空逻辑：价格首次上涨触及 initial_price
        else:
            dataframe.loc[
                (dataframe['close'] >= state['last_price']) &
                (dataframe['volume'] > 0),
                'enter_short'
            ] = 1
            dataframe.loc[
                (dataframe['close'] >= state['last_price']) &
                (dataframe['volume'] > 0),
                'enter_tag'
            ] = 'initial_short'
            
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        平仓信号生成（使用简单的 ROI 或自定义逻辑）
        """
        pair = metadata['pair']
        if pair not in self.trade_states:
            return dataframe
            
        state = self.trade_states[pair]
        direction = self.trade_direction.value
        
        # 当达到最大开仓次数且价格回升/下跌时，考虑平仓
        if state['count'] >= self.max_trades.value:
            # 做多：价格反弹 2% 时平仓
            if direction == 0:
                dataframe.loc[
                    (dataframe['close'] > dataframe['close'].shift(1)) &
                    (dataframe['volume'] > 0),
                    'exit_long'
                ] = 1
                dataframe.loc[
                    (dataframe['close'] > dataframe['close'].shift(1)) &
                    (dataframe['volume'] > 0),
                    'exit_tag'
                ] = 'profit_take_long'
            # 做空：价格反弹 2% 时平仓
            else:
                dataframe.loc[
                    (dataframe['close'] < dataframe['close'].shift(1)) &
                    (dataframe['volume'] > 0),
                    'exit_short'
                ] = 1
                dataframe.loc[
                    (dataframe['close'] < dataframe['close'].shift(1)) &
                    (dataframe['volume'] > 0),
                    'exit_tag'
                ] = 'profit_take_short'
                
        return dataframe

    def bot_start(self, **kwargs) -> None:
        """初始化策略状态"""
        self.trade_states = {}
        for pair in self.dp.current_whitelist():
            self.trade_states[pair] = {
                'count': 0,
                'last_price': self.initial_price.value
            }
        logger.info(f"Grid Trading Strategy Started. Direction: {'Long' if self.trade_direction.value == 0 else 'Short'}")
        logger.info(f"Initial Price: {self.initial_price.value}, Interval: {self.price_interval.value}, Max Trades: {self.max_trades.value}")





    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        """
        Called at the start of the bot iteration (one loop).
        Might be used to perform pair-independent tasks
        (e.g. gather some remote resource for comparison)

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-advanced/

        When not implemented by a strategy, this simply does nothing.
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
        logger.info(f"Bot loop start: {current_time}")


    def custom_entry_price(
        self,
        pair: str,
        trade: Trade | None,
        current_time: datetime,
        proposed_rate: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """
        Custom entry price logic, returning the new entry price.

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-advanced/

        When not implemented by a strategy, returns None, orderbook is used to set entry price

        :param pair: Pair that's currently analyzed
        :param trade: trade object (None for initial entries).
        :param current_time: datetime object, containing the current datetime
        :param proposed_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New entry price value if provided
        """
        return proposed_rate

    def adjust_order_price(
        self,
        trade: Trade,
        order: Order | None,
        pair: str,
        current_time: datetime,
        proposed_rate: float,
        current_order_rate: float,
        entry_tag: str | None,
        side: str,
        is_entry: bool,
        **kwargs,
    ) -> float | None:
        """
        Exit and entry order price re-adjustment logic, returning the user desired limit price.
        This only executes when a order was already placed, still open (unfilled fully or partially)
        and not timed out on subsequent candles after entry trigger.

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-callbacks/

        When not implemented by a strategy, returns current_order_rate as default.
        If current_order_rate is returned then the existing order is maintained.
        If None is returned then order gets canceled but not replaced by a new one.

        :param pair: Pair that's currently analyzed
        :param trade: Trade object.
        :param order: Order object
        :param current_time: datetime object, containing the current datetime
        :param proposed_rate: Rate, calculated based on pricing settings in entry_pricing.
        :param current_order_rate: Rate of the existing order in place.
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :param is_entry: True if the order is an entry order, False if it's an exit order.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float or None: New entry price value if provided
        """
        return current_order_rate

    def custom_exit_price(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        proposed_rate: float,
        current_profit: float,
        exit_tag: str | None,
        **kwargs,
    ) -> float:
        """
        Custom exit price logic, returning the new exit price.

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-advanced/

        When not implemented by a strategy, returns None, orderbook is used to set exit price

        :param pair: Pair that's currently analyzed
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param proposed_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param exit_tag: Exit reason.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New exit price value if provided
        """
        return proposed_rate

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """
        Customize stake size for each new trade.

        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param proposed_stake: A stake amount proposed by the bot.
        :param min_stake: Minimal stake size allowed by exchange.
        :param max_stake: Balance available for trading.
        :param leverage: Leverage selected for this trade.
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A stake size, which is between min_stake and max_stake.
        """
        return proposed_stake

    use_custom_roi = True

    def custom_roi(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        trade_duration: int,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float | None:
        """
        Custom ROI logic, returns a new minimum ROI threshold (as a ratio, e.g., 0.05 for +5%).
        Only called when use_custom_roi is set to True.

        If used at the same time as minimal_roi, an exit will be triggered when the lower
        threshold is reached. Example: If minimal_roi = {"0": 0.01} and custom_roi returns 0.05,
        an exit will be triggered if profit reaches 5%.

        :param pair: Pair that's currently analyzed.
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime.
        :param trade_duration: Current trade duration in minutes.
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the current trade.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New ROI value as a ratio, or None to fall back to minimal_roi logic.
        """
        return None

    use_custom_stoploss = True

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        """
        Custom stoploss logic, returning the new distance relative to current_rate (as ratio).
        e.g. returning -0.05 would create a stoploss 5% below current_rate.
        The custom stoploss can never be below self.stoploss, which serves as a hard maximum loss.

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-advanced/

        When not implemented by a strategy, returns the initial stoploss value.
        Only called when use_custom_stoploss is set to True.

        :param pair: Pair that's currently analyzed
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param after_fill: True if the stoploss is called after the order was filled.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return float: New stoploss value, relative to the current_rate
        """
        logger.info(f"Custom stoploss: {current_time}")

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | bool | None:
        """
        Custom exit signal logic indicating that specified position should be sold. Returning a
        string or True from this method is equal to setting sell signal on a candle at specified
        time. This method is not called when sell signal is set.

        This method should be overridden to create sell signals that depend on trade parameters. For
        example you could implement a sell relative to the candle when the trade was opened,
        or a custom 1:2 risk-reward ROI.

        Custom exit reason max length is 64. Exceeding characters will be removed.

        :param pair: Pair that's currently analyzed
        :param trade: trade object.
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param current_profit: Current profit (as ratio), calculated based on current_rate.
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return: To execute sell, return a string with custom exit reason or True. Otherwise return
        None or False.
        """
        return None

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        """
        确认开仓（可用于记录和日志）
        """
        state = self.trade_states.get(pair, {'count': 0})
        logger.info(f"Confirming {side} trade for {pair} at {rate}, count={state.get('count', 0)}")
        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        """
        确认平仓
        """
        logger.info(f"Confirming exit for {pair} at {rate}, reason: {exit_reason}")
        
        # 平仓后重置状态
        if pair in self.trade_states:
            # 延迟重置，确保交易完全关闭
            pass
            
        return True

    def check_entry_timeout(
        self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs
    ) -> bool:
        """
        Check entry timeout function callback.
        This method can be used to override the entry-timeout.
        It is called whenever a limit entry order has been created,
        and is not yet fully filled.
        Configuration options in `unfilledtimeout` will be verified before this,
        so ensure to set these timeouts high enough.

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-advanced/

        When not implemented by a strategy, this simply returns False.
        :param pair: Pair the trade is for
        :param trade: Trade object.
        :param order: Order object.
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return bool: When True is returned, then the entry order is cancelled.
        """
        return False

    def check_exit_timeout(
        self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs
    ) -> bool:
        """
        Check exit timeout function callback.
        This method can be used to override the exit-timeout.
        It is called whenever a limit exit order has been created,
        and is not yet fully filled.
        Configuration options in `unfilledtimeout` will be verified before this,
        so ensure to set these timeouts high enough.

        For full documentation please go to https://www.freqtrade.io/en/stable/strategy-advanced/

        When not implemented by a strategy, this simply returns False.
        :param pair: Pair the trade is for
        :param trade: Trade object.
        :param order: Order object.
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return bool: When True is returned, then the exit-order is cancelled.
        """
        return False

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: float | None,
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ) -> Optional[float | Tuple[float, str]]:
        """
        加仓逻辑实现
        """
        pair = trade.pair
        if pair not in self.trade_states:
            return None
            
        state = self.trade_states[pair]
        direction = self.trade_direction.value
        
        # 检查是否达到最大开仓次数
        if state['count'] >= self.max_trades.value:
            return None
            
        # 计算下一次目标价格
        # 做多：价格继续下跌
        # 做空：价格继续上涨
        next_price = self.initial_price.value + (state['count'] + 1) * self.price_interval.value
        if direction == 0:
            next_price = self.initial_price.value - (state['count'] + 1) * self.price_interval.value
            
        # 做多逻辑：当前价格 <= 下一次目标价
        if direction == 0 and current_rate <= next_price:
            # 更新状态
            self.trade_states[pair]['count'] += 1
            self.trade_states[pair]['last_price'] = next_price
            
            logger.info(
                f"Grid Buy {pair}: count={self.trade_states[pair]['count']}, "
                f"price={current_rate}, target={next_price}"
            )
            
            # 返回加仓金额（使用可用资金的固定比例）
            available_stake = self.wallets.get_available_stake_amount()
            if available_stake > 0:
                # 每次使用 20% 的可用资金（可调整）
                stake_to_use = available_stake * 0.2
                return stake_to_use, f"grid_buy_level_{self.trade_states[pair]['count']}"
                
        # 做空逻辑：当前价格 >= 下一次目标价
        elif direction == 1 and current_rate >= next_price:
            # 更新状态
            self.trade_states[pair]['count'] += 1
            self.trade_states[pair]['last_price'] = next_price
            
            logger.info(
                f"Grid Sell {pair}: count={self.trade_states[pair]['count']}, "
                f"price={current_rate}, target={next_price}"
            )
            
            # 返回加仓金额
            available_stake = self.wallets.get_available_stake_amount()
            if available_stake > 0:
                stake_to_use = available_stake * 0.2
                return stake_to_use, f"grid_sell_level_{self.trade_states[pair]['count']}"
                
        return None

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """
        Customize leverage for each new trade. This method is only called in futures mode.

        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param proposed_leverage: A leverage proposed by the bot.
        :param max_leverage: Max leverage allowed on this pair
        :param entry_tag: Optional entry_tag (buy_tag) if provided with the buy signal.
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A leverage amount, which is between 1.0 and max_leverage.
        """
        return 1.0


    def order_filled(
        self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs
    ) -> None:
        """
        Called right after an order fills.
        Will be called for all order types (entry, exit, stoploss, position adjustment).
        :param pair: Pair for trade
        :param trade: trade object.
        :param order: Order object.
        :param current_time: datetime object, containing the current datetime
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
        logger.info(f"Order filled: {current_time}")


    def plot_annotations(
        self, pair: str, start_date: datetime, end_date: datetime, dataframe: DataFrame, **kwargs
    ) -> list[AnnotationType]:
        """
        Retrieve area annotations for a chart.
        Must be returned as array, with type, label, color, start, end, y_start, y_end.
        All settings except for type are optional - though it usually makes sense to include either
        "start and end" or "y_start and y_end" for either horizontal or vertical plots
        (or all 4 for boxes).
        :param pair: Pair that's currently analyzed
        :param start_date: Start date of the chart data being requested
        :param end_date: End date of the chart data being requested
        :param dataframe: DataFrame with the analyzed data for the chart
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return: List of AnnotationType objects
        """
        return []