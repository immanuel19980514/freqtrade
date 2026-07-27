import logging
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)

"""
cd C:Projectsfreqtrade & conda activate freqtrade &

# 1. 下载历史数据
freqtrade download-data --config user_data/config_grid_trading.json --userdir user_data/ --exchange binance --pairs BTC/USDT:USDT --timeframes 5m --timerange 20260720- --trading-mode futures --erase
# 2. 运行回测
freqtrade backtesting --config user_data/config_grid_trading.json --timerange 20260720-20260723 --timeframe 5m


# 3. 启动模拟盘
freqtrade trade --config grid_config.json

"""
class GridTradingStrategy(IStrategy):
    """
    基于价格区间的网格交易策略
    """
    INTERFACE_VERSION = 3
    
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
    
    # 基础配置
    minimal_roi = {"0": 100.0}
    stoploss = -0.10
    timeframe = '5m'
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.trade_states = {}
        
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
