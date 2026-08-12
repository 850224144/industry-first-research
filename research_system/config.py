"""
配置文件
"""

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据库配置
DB_PATH = PROJECT_ROOT / "data" / "research.db"

# 缓存配置
CACHE_DIR = PROJECT_ROOT / "cache"
CACHE_EXPIRY_HOURS = 24  # 缓存过期时间（小时）

# 分析配置
ANALYSIS_CONFIG = {
    # 产品重要性评分权重
    "importance_weights": {
        "value_ratio": 0.30,          # 价值占比权重
        "substitutability": 0.30,     # 不可替代性权重
        "market_concentration": 0.20, # 市场集中度权重
        "tech_barrier": 0.20,         # 技术壁垒权重
    },

    # 产品重要性分级阈值
    "importance_thresholds": {
        "A": 80,  # A级-核心原料（西红柿）
        "B": 60,  # B级-关键部件（鸡蛋）
        "C": 40,  # C级-重要辅料（食用油）
        # D级-加分项（葱花）：< 40
    },

    # 龙头判定标准
    "leader_criteria": {
        "absolute_leader_share": 0.30,    # 绝对龙头：份额>30%
        "oligarch_share": 0.10,           # 寡头之一：份额>10%
        "follower_share": 0.05,           # 追随者：份额>5%
        "top3_concentration": 0.60,       # 前三集中度>60%为寡头垄断
    },

    # 周期判断阈值
    "cycle_thresholds": {
        "capacity_utilization_tight": 0.85,  # 产能利用率>85%为紧张
        "capacity_utilization_loose": 0.70,  # 产能利用率<70%为过剩
        "price_vs_cost_safe": 1.2,           # 价格/成本>1.2为安全
        "price_vs_cost_danger": 1.0,         # 价格/成本≤1.0为危险
    },

    # 生存能力评估
    "survival_criteria": {
        "interest_coverage_safe": 3.0,     # 利息覆盖倍数>3为安全
        "interest_coverage_risky": 1.0,    # 利息覆盖倍数<1为危险
        "debt_ratio_safe": 0.60,           # 资产负债率<60%为安全
        "debt_ratio_risky": 0.80,          # 资产负债率>80%为危险
    },
}

# 确保目录存在
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
