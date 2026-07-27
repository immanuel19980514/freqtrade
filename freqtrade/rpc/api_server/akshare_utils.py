#!/usr/bin/env python3
"""
akshare工具类 - 财经日历数据获取

功能：
1. 调用akshare的macro_info_ws和news_economic_baidu接口获取财经日历数据
2. 合并两个接口返回的数据
3. 支持按日期筛选
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

try:
    import akshare as ak
    AK_AVAILABLE = True
except ImportError:
    AK_AVAILABLE = False
    logging.warning("akshare未安装，财经日历功能不可用")


logger = logging.getLogger(__name__)

# 全局变量：存储新闻快讯数据（增量更新）
NEWS_DATAFRAME = pd.DataFrame()


class AkshareUtils:
    """
    akshare工具类
    """
    
    @staticmethod
    def get_macro_calendar(date: str = None) -> pd.DataFrame:
        """
        获取财经日历数据，合并macro_info_ws和news_economic_baidu两个接口
        
        Args:
            date: 日期字符串，格式如 '20260605'，不传则获取最近的数据
            
        Returns:
            pd.DataFrame: 合并后的财经日历数据
            
        示例:
            df = AkshareUtils.get_macro_calendar('20260605')
        """
        if not AK_AVAILABLE:
            logger.error("akshare未安装，无法获取财经日历数据")
            return pd.DataFrame()
        
        logger.info(f"开始获取财经日历数据，日期: {date}")
        
        df_macro = pd.DataFrame()
        df_news = pd.DataFrame()
        
        # 1. 获取macro_info_ws数据（带异常处理）
        try:
            logger.info("正在调用 macro_info_ws 接口...")
            df_macro = ak.macro_info_ws(date)
            logger.info(f"macro_info_ws 返回 {len(df_macro)} 条数据")
            logger.debug(f"macro_info_ws 列名: {list(df_macro.columns)}")
        except Exception as e:
            logger.warning(f"macro_info_ws 调用失败: {e}")
            logger.info("将跳过 macro_info_ws 接口，继续尝试其他接口")
        
        # 2. 获取news_economic_baidu数据（带异常处理）
        try:
            logger.info("正在调用 news_economic_baidu 接口...")
            df_news = ak.news_economic_baidu(date)
            logger.info(f"news_economic_baidu 返回 {len(df_news)} 条数据")
            logger.debug(f"news_economic_baidu 列名: {list(df_news.columns)}")
        except Exception as e:
            logger.warning(f"news_economic_baidu 调用失败: {e}")
            logger.info("将跳过 news_economic_baidu 接口")
        
        # 3. 检查是否所有接口都失败
        if df_macro.empty and df_news.empty:
            logger.error("所有接口都获取数据失败，请检查网络连接")
            return pd.DataFrame()
        
        # 4. 数据预处理
        if not df_macro.empty:
            df_macro = AkshareUtils._preprocess_macro(df_macro)
        if not df_news.empty:
            df_news = AkshareUtils._preprocess_news(df_news)
        
        # 5. 合并两个DataFrame
        merged_df = AkshareUtils._merge_dataframes(df_macro, df_news)
        logger.info(f"合并后数据: {len(merged_df)} 条")
        logger.debug(f"合并后列名: {list(merged_df.columns)}")

        # 按照日期、时间、地区、事件进行排序
        sort_cols = []
        sort_ascending = []
        
        if '日期' in merged_df.columns:
            sort_cols.append('日期')
            sort_ascending.append(False)  # 日期降序（最新的在前）
        
        if '时间' in merged_df.columns:
            sort_cols.append('时间')
            sort_ascending.append(True)  # 时间升序
        
        if '地区' in merged_df.columns:
            sort_cols.append('地区')
            sort_ascending.append(True)  # 地区升序
        
        if '事件' in merged_df.columns:
            sort_cols.append('事件')
            sort_ascending.append(True)  # 事件升序
        
        if sort_cols:
            merged_df = merged_df.sort_values(by=sort_cols, ascending=sort_ascending)
            logger.info(f"按 {sort_cols} 排序完成")
        
        return merged_df
    
    @staticmethod
    def _preprocess_macro(df: pd.DataFrame) -> pd.DataFrame:
        """
        预处理macro_info_ws数据
        
        Args:
            df: macro_info_ws返回的DataFrame
            
        Returns:
            pd.DataFrame: 预处理后的DataFrame
        """
        if df.empty:
            return df
            
        # 复制一份避免修改原数据
        result = df.copy()
        
        # 列名处理：统一前缀，避免与news_economic_baidu冲突
        # macro_info_ws 典型列: 日期, 时间, 国家, 数据, 前值, 预期, 公布值, 重要性
        # rename_map = {}
        # for col in result.columns:
        #     if col not in ['时间']:
        #         rename_map[col] = f"macro_{col}"
        # result = result.rename(columns=rename_map)
        
            
        
        # 时间格式统一
        if '时间' in result.columns:
            result['日期'] = pd.to_datetime(result['时间']).dt.strftime('%Y-%m-%d')
            result['时间'] = pd.to_datetime(result['时间']).dt.strftime('%H:%M')
        
        # 增加来源列，标记为"WS"（表示来自macro_info_ws接口）
        result['来源'] = 'WS'
        
        return result
    
    @staticmethod
    def _preprocess_news(df: pd.DataFrame) -> pd.DataFrame:
        """
        预处理news_economic_baidu数据
        
        Args:
            df: news_economic_baidu返回的DataFrame
            
        Returns:
            pd.DataFrame: 预处理后的DataFrame
        """
        if df.empty:
            return df
            
        # 复制一份避免修改原数据
        result = df.copy()
        
        # 列名处理：统一前缀
        # news_economic_baidu 典型列: 日期, 时间, 地区, 事件, 公布, 预期, 前值, 重要性
        # rename_map = {}
        # for col in result.columns:
        #     if col not in ['日期', '时间']:
        #         rename_map[col] = f"news_{col}"
        # result = result.rename(columns=rename_map)


        
        # 日期格式统一
        if '日期' in result.columns:
            result['日期'] = pd.to_datetime(result['日期']).dt.strftime('%Y-%m-%d')

        result['来源'] = 'BD'
        
        # # 时间格式统一
        # if '时间' in result.columns:
        #     result['时间'] = result['时间'].fillna('')
        
        return result
    
    @staticmethod
    def _merge_dataframes(df_macro: pd.DataFrame, df_news: pd.DataFrame) -> pd.DataFrame:
        """
        合并两个DataFrame
        
        Args:
            df_macro: 预处理后的macro_info_ws数据
            df_news: 预处理后的news_economic_baidu数据
            
        Returns:
            pd.DataFrame: 合并后的DataFrame
        """
        # 如果其中一个为空，返回另一个
        if df_macro.empty:
            return df_news
        if df_news.empty:
            return df_macro
        
        # 使用concat合并，保留所有行
        merged = pd.concat([df_macro, df_news], ignore_index=True)
        
        # 如果有重复数据（相同日期+时间+地区+事件），去重

        duplicate_cols = []
        if '日期' in merged.columns:
            duplicate_cols.append('日期')
        if '时间' in merged.columns:
            duplicate_cols.append('时间')
        if '地区' in merged.columns:
            duplicate_cols.append('地区')
        if '事件' in merged.columns:
            duplicate_cols.append('事件')
        
        if duplicate_cols:
            merged = merged.drop_duplicates(subset=duplicate_cols, keep='first')
        
        # 按日期和时间排序
        sort_cols = []
        if '日期' in merged.columns:
            sort_cols.append('日期')
        if '时间' in merged.columns:
            sort_cols.append('时间')
        
        if sort_cols:
            merged = merged.sort_values(by=sort_cols, ascending=[False, True])
        
        return merged.reset_index(drop=True)
    
    # @staticmethod
    # def _filter_by_date(df: pd.DataFrame, date: str) -> pd.DataFrame:
    #     """
    #     按日期筛选数据
        
    #     Args:
    #         df: 数据DataFrame
    #         date: 日期字符串，格式如 '20260605'
            
    #     Returns:
    #         pd.DataFrame: 筛选后的数据
    #     """
    #     if df.empty or '日期' not in df.columns:
    #         return df
            
    #     try:
    #         # 将输入日期转换为标准格式
    #         target_date = datetime.strptime(date, '%Y%m%d').strftime('%Y-%m-%d')
    #         return df[df['日期'] == target_date].reset_index(drop=True)
    #     except ValueError:
    #         logger.error(f"日期格式错误: {date}，期望格式: YYYYMMDD")
    #         return df
    
    @staticmethod
    def print_dataframe(df: pd.DataFrame, title: str = "宏观数据"):
        """
        格式化打印 DataFrame
        
        Args:
            df: 要打印的 DataFrame
            title: 标题
        """
        if df.empty:
            print(f"{title}: 无数据")
            return
        
        print("\n" + "=" * 80)
        print(f"{title}")
        print("=" * 80)
        
        # 设置 pandas 显示选项
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", None)
        pd.set_option("display.max_colwidth", 50)
        
        # 打印 DataFrame
        print(df.to_string())
        print("\n" + "=" * 80)
        
        # 打印列信息
        print(f"\n列名: {list(df.columns)}")
        print(f"数据行数: {len(df)}")
    
    # ==================== 新闻快讯相关方法 ====================
    
    @staticmethod
    def get_news_flash(news_interfaces_names: str = None) -> list[pd.DataFrame]:
        """
        获取并整合5个新闻快讯接口的数据
        
        Args:
            news_interfaces_names: 要获取的新闻快讯接口名称，逗号分隔，默认获取所有接口
        
        Returns:
            pd.DataFrame: 整合后的新闻快讯数据，包含标题、内容、发布日期、发布时间、链接、来源
        
        接口列表:
        - stock_info_global_sina: 新浪财经
        - stock_info_global_cls: 财联社
        - stock_info_global_futu: 富途牛牛
        - stock_info_global_em: 东方财富
        - stock_info_global_ths: 同花顺
        """
        global NEWS_DATAFRAME
        
        
        logger.info("开始获取新闻快讯数据")
        
        # 定义接口配置
        news_interfaces = [
            {"name": "stock_info_global_sina", "source": "新浪财经"},
            #{"name": "stock_info_global_cls", "source": "财联社"},
            {"name": "stock_info_global_futu", "source": "富途牛牛"},
            {"name": "stock_info_global_em", "source": "东方财富"},
            {"name": "stock_info_global_ths", "source": "同花顺"},
        ]
        
        # 过滤出指定接口
        if news_interfaces_names:
            news_interfaces = [interface for interface in news_interfaces if interface['name'] in news_interfaces_names.split(',')]
        
        # 存储所有接口的数据
        all_dfs = []
        
        for interface in news_interfaces:
            try:
                logger.info(f"正在调用 {interface['name']} 接口...")
                # 动态调用akshare方法
                ak_func = getattr(ak, interface['name'])
                df = ak_func()
                logger.info(f"{interface['name']} 返回 {len(df)} 条数据")
                
                # 预处理数据
                df = AkshareUtils._preprocess_news_flash(df, interface['source'])
                all_dfs.append(df)
                
            except Exception as e:
                logger.warning(f"{interface['name']} 调用失败: {e}")
                continue

        if not all_dfs:
            logger.error("所有新闻快讯接口都获取数据失败")

        return all_dfs
    
    
    @staticmethod
    def _preprocess_news_flash(df: pd.DataFrame, source: str) -> pd.DataFrame:
        """
        预处理新闻快讯数据，统一格式
        
        Args:
            df: 原始DataFrame
            source: 数据来源标识
            
        Returns:
            pd.DataFrame: 统一格式后的DataFrame，包含：标题、内容、发布日期、发布时间、链接、来源
        """
        if df.empty:
            return df
            
        result = df.copy()
        
        # 定义字段映射规则
        field_mapping = {
            # 标题，快讯的标题可能为空，以内容代替
            '标题': ['标题'],
            # 内容/摘要字段
            '内容': ['内容', '摘要'],
            # 发布日期
            '发布日期': ['发布日期'],
            # 发布时间字段（可能包含日期和时间）
            '发布时间': ['发布时间', '时间'],
            # 链接字段
            '链接': ['链接'],
        }
        
        # 映射字段
        for target_col, source_cols in field_mapping.items():
            for source_col in source_cols:
                if source_col in result.columns:
                    result[target_col] = result[source_col]
                    break
            if target_col not in result.columns:
                result[target_col] = ''
        
        # 处理发布时间，拆分为日期和时间
        if '发布时间' in result.columns:
            result['发布时间'] = result['发布时间'].astype(str)
            # 尝试拆分日期和时间
            try:
                # 尝试解析时间格式
                parsed_time = pd.to_datetime(result['发布时间'], errors='coerce')
                result['发布日期'] = parsed_time.dt.strftime('%Y-%m-%d')
                result['发布时间'] = parsed_time.dt.strftime('%H:%M:%S')
                
                # 如果解析失败，尝试手动拆分
                mask = result['发布日期'].isna()
                if mask.any():
                    result.loc[mask, '发布日期'] = result.loc[mask, '发布时间'].str.extract(r'(\d{4}-\d{2}-\d{2})')[0]
                    result.loc[mask, '发布时间'] = result.loc[mask, '发布时间'].str.extract(r'(\d{2}:\d{2}(:\d{2})?)')[0]
            except Exception as e:
                logger.debug(f"时间格式解析失败: {e}")
                result['发布日期'] = ''
                result['发布时间'] = result['发布时间'].str[-8:] if len(result['发布时间'].iloc[0]) > 8 else result['发布时间']
        
        # 如果没有单独的日期字段，创建一个
        if '发布日期' not in result.columns:
            result['发布日期'] = ''
        
        # 添加来源列
        result['来源'] = source
        
        # 只保留需要的列
        keep_cols = ['标题', '内容', '发布日期', '发布时间', '链接', '来源']
        result = result[keep_cols]
        
        # 处理空值
        result = result.fillna('')
        
        return result
    
    @staticmethod
    def incremental_merge(new_dfs: list[pd.DataFrame]) -> pd.DataFrame:
        """
        合并数据，根据来源、发布日期、发布时间、标题判断是否重复
        
        Args:
            new_dfs: 新获取的DataFrame列表
            
        Returns:
            pd.DataFrame: 合并去重后的DataFrame
        """
        
        merge_df = pd.DataFrame()
        if not new_dfs:
            return merge_df

        # 合并所有接口数据
        merge_df = pd.concat(new_dfs, ignore_index=True)
        logger.info(f"合并后数据: {len(merge_df)} 条")

        
        # 去重：根据来源、发布日期、发布时间、标题判断重复
        duplicate_cols = ['来源', '发布日期', '发布时间', '标题']
        # 确保所有去重列都存在
        duplicate_cols = [col for col in duplicate_cols if col in merge_df.columns]
        
        if duplicate_cols:
            before_count = len(merge_df)
            merge_df = merge_df.drop_duplicates(subset=duplicate_cols, keep='first')
            after_count = len(merge_df)
            logger.info(f"去重完成，移除 {before_count - after_count} 条重复数据")
        
        # 按时间排序
        merge_df = AkshareUtils._sort_by_time(merge_df)

        logger.info(f"增量合并完成，全局数据共 {len(merge_df)} 条")
        
        return merge_df
    
    @staticmethod
    def _sort_by_time(df: pd.DataFrame) -> pd.DataFrame:
        """
        按发布日期和时间排序，最新的在前
        
        Args:
            df: 要排序的DataFrame
            
        Returns:
            pd.DataFrame: 排序后的DataFrame
        """
        sort_cols = []
        sort_ascending = []
        
        if '发布日期' in df.columns:
            sort_cols.append('发布日期')
            sort_ascending.append(False)  # 日期降序
        
        if '发布时间' in df.columns:
            sort_cols.append('发布时间')
            sort_ascending.append(False)  # 时间降序
        
        if sort_cols:
            df = df.sort_values(by=sort_cols, ascending=sort_ascending)
        
        return df.reset_index(drop=True)
    
    @staticmethod
    def get_news_dataframe() -> pd.DataFrame:
        """
        获取全局新闻快讯DataFrame
        
        Returns:
            pd.DataFrame: 全局新闻快讯数据
        """
        return NEWS_DATAFRAME
    
    @staticmethod
    def clear_news_dataframe():
        """
        清空全局新闻快讯DataFrame
        """
        global NEWS_DATAFRAME
        NEWS_DATAFRAME = pd.DataFrame()
        logger.info("已清空全局新闻快讯数据")

