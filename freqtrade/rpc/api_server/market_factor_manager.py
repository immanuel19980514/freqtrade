#!/usr/bin/env python3
"""
全球金融市场影响因素管理器

功能：
1. 定义和管理金融市场影响因素
2. 定义和管理因素之间的影响关系
3. 提供因素和因素关系的查询方法
"""

import json
import logging
import os
import random
import re
from typing import List, Dict, Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FACTORS_FILE = os.path.join(PROJECT_ROOT, "user_data", "market_factor.json")


class MarketFactorManager:
    """
    全球金融市场影响因素管理器
    
    功能：
    - 管理因素列表（名称、分类、国家、说明）
    - 管理因素关系（源头因素、结果因素、权重、利好或利空、说明）
    - 提供查询方法
    - 提供颜色映射功能
    """
    
    # ==================== 缓存定义 ====================
    _factors_cache: Optional[pd.DataFrame] = None
    _relations_cache: Optional[pd.DataFrame] = None
    
    # ==================== 颜色映射定义 ====================
    # 分类颜色映射
    CATEGORY_COLORS: Dict[str, str] = {
        "宏观经济": "#5470C6",      # 蓝色
        "地缘政治": "#91CC75",      # 绿色
        "供需关系": "#FAC858",      # 黄色
        "市场情绪": "#EE6666",      # 红色
        "技术指标": "#73C0DE",      # 青色
        "政策法规": "#9A60B4",      # 紫色
    }
    
    # 国家/地区颜色映射
    COUNTRY_COLORS: Dict[str, str] = {
        "全球": "#666666",          # 灰色
        "美国": "#FF0000",          # 红色
        "中国": "#FF6600",          # 橙色
        "欧盟": "#0066FF",          # 蓝色
        "日本": "#00CC00",          # 绿色
        "香港": "#CC66FF",          # 紫色
        
        "亚洲": "#FFCC00",          # 黄色
    }
    
    # ==================== 因素定义 ====================
    # 二维数组：每个因素包含 [状态, 分类, 国家, 名称, 说明]
    # 状态：1=有效，0=无效
    
    
    # ==================== 因素关系定义 ====================
    # 二维数组：每个关系包含 [结果因素, 源头因素, 权重, 利好或利空, 说明]
    # 权重：1-100，表示影响程度100%中的占比
    # 利好或利空：利好/利空
    
    
    @staticmethod
    def _load_factors_from_file() -> pd.DataFrame:
        """
        从文件加载因素数据
        
        Returns:
            pd.DataFrame: 因素列表
        """
        try:
            with open(FACTORS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用分隔符分割 FACTORS 和 FACTOR_RELATIONS
            parts = content.split('__FACTOR_RELATIONS__')
            factors_json = parts[0].strip()
            
            # 解析 JSON
            factors_json = re.sub(r"//.*|\/\*[\s\S]*?\*\/", "", factors_json)
            factors_data = json.loads(factors_json)
            
            # 第一行是列名，其余是数据
            columns = factors_data[0]
            data = factors_data[1:]
            
            df = pd.DataFrame(data, columns=columns)
            logger.info(f"从文件加载因素列表，共 {len(df)} 个因素")
            return df
        except Exception as e:
            logger.error(f"从文件加载因素数据失败: {e}")
            return pd.DataFrame(columns=["状态", "分类", "国家", "名称", "说明"])
    
    @staticmethod
    def _load_relations_from_file() -> pd.DataFrame:
        """
        从文件加载因素关系数据
        
        Returns:
            pd.DataFrame: 因素关系列表
        """
        try:
            with open(FACTORS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用分隔符分割 FACTORS 和 FACTOR_RELATIONS
            parts = content.split('__FACTOR_RELATIONS__')
            if len(parts) < 2:
                logger.warning("文件中未找到 FACTOR_RELATIONS 数据")
                return pd.DataFrame(columns=["结果因素", "源头因素", "权重", "利好或利空", "说明"])
            
            relations_json = parts[1].strip()
            
            # 解析 JSON
            relations_json = re.sub(r"//.*|\/\*[\s\S]*?\*\/", "", relations_json)
            relations_data = json.loads(relations_json)

            
            # 第一行是列名，其余是数据
            columns = relations_data[0]
            data = relations_data[1:]
            
            df = pd.DataFrame(data, columns=columns)
            logger.info(f"从文件加载因素关系列表，共 {len(df)} 个关系")
            return df
        except Exception as e:
            logger.error(f"从文件加载因素关系数据失败: {e}")
            return pd.DataFrame(columns=["结果因素", "源头因素", "权重", "利好或利空", "说明"])
    
    @staticmethod
    def get_factors(refresh: bool = False) -> pd.DataFrame:
        """
        获取因素列表
        
        Args:
            refresh: 是否强制从文件刷新数据，默认False使用缓存
            
        Returns:
            pd.DataFrame: 因素列表，包含状态、分类、国家、名称、说明字段
        """
        if refresh or MarketFactorManager._factors_cache is None:
            MarketFactorManager._factors_cache = MarketFactorManager._load_factors_from_file()
        
        logger.info(f"获取因素列表，共 {len(MarketFactorManager._factors_cache)} 个因素")
        return MarketFactorManager._factors_cache
    
    @staticmethod
    def get_factor_relations(refresh: bool = False) -> pd.DataFrame:
        """
        获取因素关系列表
        
        Args:
            refresh: 是否强制从文件刷新数据，默认False使用缓存
            
        Returns:
            pd.DataFrame: 因素关系列表，包含源头因素、结果因素、权重、利好或利空、说明字段
        """
        if refresh or MarketFactorManager._relations_cache is None:
            MarketFactorManager._relations_cache = MarketFactorManager._load_relations_from_file()
        
        logger.info(f"获取因素关系列表，共 {len(MarketFactorManager._relations_cache)} 个关系")
        return MarketFactorManager._relations_cache
    
    @staticmethod
    def get_factors_by_category(category: str) -> pd.DataFrame:
        """
        按分类获取因素列表
        
        Args:
            category: 分类名称
            
        Returns:
            pd.DataFrame: 指定分类的因素列表
        """
        df = MarketFactorManager.get_factors()
        result = df[df["分类"] == category]
        
        logger.info(f"获取分类 '{category}' 的因素，共 {len(result)} 个")
        
        return result
    
    @staticmethod
    def get_factors_by_country(country: str) -> pd.DataFrame:
        """
        按国家获取因素列表
        
        Args:
            country: 国家名称
            
        Returns:
            pd.DataFrame: 指定国家的因素列表
        """
        df = MarketFactorManager.get_factors()
        result = df[df["国家"] == country]
        
        logger.info(f"获取国家 '{country}' 的因素，共 {len(result)} 个")
        
        return result
    
    @staticmethod
    def get_relations_by_source(source_factor: str) -> pd.DataFrame:
        """
        按源头因素获取关系列表
        
        Args:
            source_factor: 源头因素名称
            
        Returns:
            pd.DataFrame: 指定源头因素的关系列表
        """
        df = MarketFactorManager.get_factor_relations()
        result = df[df["源头因素"] == source_factor]
        
        logger.info(f"获取源头因素 '{source_factor}' 的关系，共 {len(result)} 个")
        
        return result
    
    @staticmethod
    def get_relations_by_result(result_factor: str) -> pd.DataFrame:
        """
        按结果因素获取关系列表
        
        Args:
            result_factor: 结果因素名称
            
        Returns:
            pd.DataFrame: 指定结果因素的关系列表
        """
        df = MarketFactorManager.get_factor_relations()
        result = df[df["结果因素"] == result_factor]
        
        logger.info(f"获取结果因素 '{result_factor}' 的关系，共 {len(result)} 个")
        
        return result
    
    @staticmethod
    def get_factor_categories() -> List[str]:
        """
        获取所有因素分类
        
        Returns:
            List[str]: 分类列表
        """
        df = MarketFactorManager.get_factors()
        categories = df["分类"].unique().tolist()
        
        logger.info(f"获取因素分类，共 {len(categories)} 个分类: {categories}")
        
        return categories
    
    @staticmethod
    def get_factor_countries() -> List[str]:
        """
        获取所有因素国家
        
        Returns:
            List[str]: 国家列表
        """
        df = MarketFactorManager.get_factors()
        countries = df["国家"].unique().tolist()
        
        logger.info(f"获取因素国家，共 {len(countries)} 个国家: {countries}")
        
        return countries
    
    @staticmethod
    def get_category_color(category: str) -> str:
        """
        根据分类获取颜色
        
        Args:
            category: 分类名称
            
        Returns:
            str: 颜色代码（十六进制），如果不存在则返回随机颜色
        """
        # 查找预定义颜色
        if category in MarketFactorManager.CATEGORY_COLORS:
            return MarketFactorManager.CATEGORY_COLORS[category]
        
        # 生成随机颜色
        random_color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        logger.debug(f"分类 '{category}' 未找到预定义颜色，使用随机颜色: {random_color}")
        
        return random_color
    
    @staticmethod
    def get_country_color(country: str) -> str:
        """
        根据国家获取颜色
        
        Args:
            country: 国家名称
            
        Returns:
            str: 颜色代码（十六进制），如果不存在则返回随机颜色
        """
        # 查找预定义颜色
        if country in MarketFactorManager.COUNTRY_COLORS:
            return MarketFactorManager.COUNTRY_COLORS[country]
        
        # 生成随机颜色
        random_color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        logger.debug(f"国家 '{country}' 未找到预定义颜色，使用随机颜色: {random_color}")
        
        return random_color
    
    @staticmethod
    def print_factors():
        """
        打印因素列表（调试用）
        """
        df = MarketFactorManager.get_factors()
        print("\n" + "=" * 80)
        print("全球金融市场影响因素列表")
        print("=" * 80)
        print(df.to_string())
        print("\n" + "=" * 80)
        print(f"共 {len(df)} 个因素")
    
    @staticmethod
    def print_factor_relations():
        """
        打印因素关系列表（调试用）
        """
        df = MarketFactorManager.get_factor_relations()
        print("\n" + "=" * 80)
        print("因素影响关系列表")
        print("=" * 80)
        print(df.to_string())
        print("\n" + "=" * 80)
        print(f"共 {len(df)} 个关系")


# 测试代码
if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 打印因素列表
    MarketFactorManager.print_factors()
    
    # 打印因素关系列表
    MarketFactorManager.print_factor_relations()
    
    # 测试按分类查询
    print("\n宏观经济因素:")
    macro_factors = MarketFactorManager.get_factors_by_category("宏观经济")
    print(macro_factors.to_string())
    
    # 测试按国家查询
    print("\n美国因素:")
    us_factors = MarketFactorManager.get_factors_by_country("美国")
    print(us_factors.to_string())
    
    # 测试按源头因素查询关系
    print("\n美联储利率决议的影响:")
    fed_relations = MarketFactorManager.get_relations_by_source("美联储利率决议")
    print(fed_relations.to_string())
    
    # 测试按结果因素查询关系
    print("\n影响黄金价格的因素:")
    gold_relations = MarketFactorManager.get_relations_by_result("黄金价格")
    print(gold_relations.to_string())
    
    # 获取所有分类和国家
    print("\n所有分类:", MarketFactorManager.get_factor_categories())
    print("所有国家:", MarketFactorManager.get_factor_countries())