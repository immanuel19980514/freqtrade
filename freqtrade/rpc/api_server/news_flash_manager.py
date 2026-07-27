#!/usr/bin/env python3
"""
新闻快讯定时任务管理器

功能：
1. 定时调用akshare的新闻快讯接口
2. 按小时存储数据，支持增量合并
3. 自动清理超过24小时的历史数据
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List
from zoneinfo import ZoneInfo

import pandas as pd

from freqtrade.rpc.api_server.akshare_utils import AkshareUtils

logger = logging.getLogger(__name__)


class NewsFlashManager:
    """
    新闻快讯管理器
    
    功能：
    - 定时调用新闻接口
    - 按小时存储数据
    - 增量合并去重
    - 自动清理历史数据
    """
    
    def __init__(self):
        # 按小时存储数据的字典，key为"YYYY-MM-DD HH:00:00"格式的小时标识
        self.hourly_data: Dict[str, pd.DataFrame] = {}
        
        # 定时器线程
        self.timer_thread: threading.Timer = None
        
        # 运行状态
        self.running = False
        
        # 上次调用时间
        self.last_call_time = None
        
        # 时区
        self.timezone = ZoneInfo("Asia/Shanghai")
    
    def start(self):
        """
        启动定时任务管理器
        
        初次启动时立即调用一次接口，然后开始定时调度
        """
        if self.running:
            logger.info("新闻快讯管理器已经在运行中")
            return
        
        self.running = True
        logger.info("启动新闻快讯管理器")
        
        # 初次启动时立即调用一次全部接口
        # logger.info("初次启动，立即调用全部接口")
        # self.run_task_now()  改为外部start（）之后手动调用
        
        # 启动定时任务
        self._schedule_next_task()
    
    def stop(self):
        """
        停止定时任务管理器
        """
        self.running = False
        
        if self.timer_thread:
            self.timer_thread.cancel()
            self.timer_thread = None
        
        logger.info("已停止新闻快讯管理器")
    
    def _schedule_next_task(self):
        """
        调度下一个定时任务
        """
        if not self.running:
            return
        
        now = datetime.now(self.timezone)
        current_minute = now.minute
        current_second = now.second
        
        # 计算下一个任务的时间
        # 目标分钟：5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 0(60)
        target_minutes = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 0]
        
        # 找到下一个目标分钟
        next_minute = None
        for target in target_minutes:
            if target > current_minute:
                next_minute = target
                break

        # 如果没有找到，说明需要到下一小时
        if next_minute is None:
            next_minute = target_minutes[0]
            wait_minutes = (60 - current_minute) + next_minute
        else:
            wait_minutes = next_minute - current_minute

        # 计算等待时间（秒）
        wait_seconds = wait_minutes * 60 - current_second

        # 设置定时器
        self.timer_thread = threading.Timer(wait_seconds, self._run_scheduled_task)
        self.timer_thread.start()

        logger.debug(f"下次任务调度：{wait_seconds}秒后（{next_minute}分钟）")

    def run_task_now(self):
        """
        立即执行定时任务，获取所有接口的数据
        """
        if not self.running:
            return

        logger.info(f"立即执行定时任务，获取所有接口的数据")

        try:
            dfs = AkshareUtils.get_news_flash()
            merge_df = AkshareUtils.incremental_merge(dfs)
            if not merge_df.empty:
                self._merge_to_hourly_data(merge_df)
        except Exception as e:
            logger.error(f"任务执行失败: {e}", exc_info=True)


    def _run_scheduled_task(self):
        """
        执行定时任务
        """
        if not self.running:
            return

        now = datetime.now(self.timezone)
        current_minute = now.minute

        logger.info(f"执行定时任务，当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # 判断执行哪个任务
            interface_names = "" #调用全部5个新闻接口
            if current_minute not in [30, 0]:  # 0表示60分钟，即整点
                interface_names = "stock_info_global_sina,stock_info_global_cls"  ## 其他逢5分钟调用新浪和财联社两个接口

            dfs = AkshareUtils.get_news_flash(interface_names)
            merge_df = AkshareUtils.incremental_merge(dfs)
            if not merge_df.empty:
                self._merge_to_hourly_data(merge_df)

            # 清理超过24小时的数据
            self._clean_old_data()

        except Exception as e:
            logger.error(f"定时任务执行失败: {e}", exc_info=True)

        finally:
            # 调度下一个任务
            self._schedule_next_task()
    
    
    
    def _merge_to_hourly_data(self, new_df: pd.DataFrame):
        """
        将新数据按发布时间自动划分并合并到对应小时的dataframe
        
        Args:
            new_df: 新获取的数据，需要包含'发布日期'和'发布时间'字段
        """
        if new_df.empty:
            return
        
        # 复制一份避免修改原数据
        df = new_df.copy()
        
        # 新增'所属小时'字段，标识每条数据所属的时间段
        df['所属小时'] = self._calculate_hour_key(df)
        
        # 按'所属小时'分组
        grouped = df.groupby('所属小时')
        
        # 统计各小时的数据量
        hour_stats = []
        
        # 遍历每个小时分组，合并到对应的数据
        for hour_key, group_df in grouped:
            # 移除'所属小时'字段（不需要存储）
            group_df = group_df.drop(columns=['所属小时'])
            
            # 获取该小时已存在的数据
            existing_df = self.hourly_data.get(hour_key, pd.DataFrame())
            
            # 增量合并
            merged_df = AkshareUtils.incremental_merge([existing_df, group_df])
            
            # 更新到字典
            self.hourly_data[hour_key] = merged_df
            
            hour_stats.append(f"{hour_key}: {len(group_df)}条")
            logger.debug(f"已合并到 {hour_key}，新增 {len(group_df)} 条，当前共 {len(merged_df)} 条")
        
        logger.info(f"数据划分合并完成，涉及 {len(grouped)} 个小时: {', '.join(hour_stats)}")
    
    def _calculate_hour_key(self, df: pd.DataFrame) -> pd.Series:
        """
        计算每条数据所属的小时标识
        
        Args:
            df: 包含'发布日期'和'发布时间'字段的DataFrame
            
        Returns:
            pd.Series: 每条数据的所属小时标识，格式为"YYYY-MM-DD HH:00:00"
        """
        # 创建默认的小时标识（使用当前时间）
        default_key = datetime.now(self.timezone).strftime("%Y-%m-%d %H:00:00")
        result = pd.Series([default_key] * len(df))
        
        # 如果有发布日期字段
        if '发布日期' in df.columns:
            # 遍历每一行计算所属小时
            for idx, row in df.iterrows():
                try:
                    date_str = str(row['发布日期']).strip()
                    time_str = str(row.get('发布时间', '')).strip()
                    
                    if date_str and date_str not in ['nan', 'None', '']:
                        # 解析日期
                        date_part = datetime.strptime(date_str, '%Y-%m-%d').date()
                        
                        # 解析时间（取小时部分）
                        hour = 0
                        if time_str and time_str not in ['nan', 'None', '']:
                            try:
                                if len(time_str) >= 5:  # 至少有 HH:MM
                                    time_part = datetime.strptime(time_str[:5], '%H:%M')
                                    hour = time_part.hour
                            except ValueError:
                                pass
                        
                        # 构建小时标识
                        hour_key = f"{date_part.strftime('%Y-%m-%d')} {hour:02d}:00:00"
                        result.iloc[idx] = hour_key
                except Exception as e:
                    logger.debug(f"计算所属小时失败: {e}")
                    continue
        
        return result
    
    def _clean_old_data(self):
        """
        删除超过24小时之前的数据
        """
        now = datetime.now(self.timezone)
        threshold = now - timedelta(hours=24)
        threshold_key = threshold.strftime("%Y-%m-%d %H:00:00")
        
        # 获取需要删除的key列表
        keys_to_delete = []
        for key in self.hourly_data.keys():
            if key < threshold_key:
                keys_to_delete.append(key)
        
        # 删除旧数据
        for key in keys_to_delete:
            del self.hourly_data[key]
            logger.debug(f"删除过期数据: {key}")
        
        if keys_to_delete:
            logger.info(f"清理了 {len(keys_to_delete)} 个过期的小时数据")
    
    def get_all_data(self) -> pd.DataFrame:
        """
        获取所有小时的数据合并后的完整DataFrame
        
        Returns:
            pd.DataFrame: 所有数据合并后的DataFrame
        """
        if not self.hourly_data:
            return pd.DataFrame()
        
        # 合并所有小时的数据
        all_dfs = list(self.hourly_data.values())
        merged = pd.concat(all_dfs, ignore_index=True)
        
        # 去重和排序
        duplicate_cols = ['来源', '发布日期', '发布时间', '标题']
        duplicate_cols = [col for col in duplicate_cols if col in merged.columns]
        
        if duplicate_cols:
            merged = merged.drop_duplicates(subset=duplicate_cols, keep='first')
        
        # 按时间排序
        merged = AkshareUtils._sort_by_time(merged)
        
        return merged
    
    def get_hour_data(self, hour_key: str) -> pd.DataFrame:
        """
        获取指定小时的数据
        
        Args:
            hour_key: 小时标识，格式如 "YYYY-MM-DD HH:00:00"
            
        Returns:
            pd.DataFrame: 指定小时的数据
        """
        return self.hourly_data.get(hour_key, pd.DataFrame())
    
    def get_hour_keys(self) -> List[str]:
        """
        获取所有存储的小时标识列表
        
        Returns:
            List[str]: 小时标识列表，按时间排序
        """
        return sorted(self.hourly_data.keys())
    
    def get_data_summary(self) -> Dict[str, int]:
        """
        获取数据汇总信息
        
        Returns:
            Dict[str, int]: 汇总信息，包含总数据量和小时数量
        """
        total_rows = sum(len(df) for df in self.hourly_data.values())
        return {
            "hours_count": len(self.hourly_data),
            "total_rows": total_rows
        }


# 全局单例
_news_manager = None


def get_news_manager() -> NewsFlashManager:
    """
    获取新闻快讯管理器单例
    
    Returns:
        NewsFlashManager: 新闻快讯管理器实例
    """
    global _news_manager
    if _news_manager is None:
        _news_manager = NewsFlashManager()
    return _news_manager


# 测试代码
if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 创建管理器
    manager = get_news_manager()
    
    # 启动管理器
    manager.start()
    
    # 运行一段时间后停止
    try:
        # 运行5分钟
        time.sleep(5 * 60)
    finally:
        manager.stop()
        
        # 打印数据汇总
        summary = manager.get_data_summary()
        print(f"\n数据汇总: {summary}")
        
        # 打印小时列表
        hours = manager.get_hour_keys()
        print(f"存储的小时: {hours}")