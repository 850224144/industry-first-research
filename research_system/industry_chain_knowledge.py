"""
产业链知识库 - "西红柿炒鸡蛋"逻辑的核心
"""

from typing import Dict, List, Optional


class IndustryChain:
    """产业链配置类"""

    def __init__(self, name: str, chain_flow: str, description: str):
        self.name = name
        self.chain_flow = chain_flow
        self.description = description
        self.products = {}
        self.companies = {}

    def add_product(self, product_name: str, config: Dict):
        """添加产品配置"""
        self.products[product_name] = config

    def add_company(self, company_name: str, stock_code: str, products: List[str], position: str):
        """添加公司配置"""
        self.companies[stock_code] = {
            'name': company_name,
            'products': products,
            'position': position,
        }

    def get_company_analysis(self, stock_code: str) -> Optional[Dict]:
        """获取公司的产业链分析"""
        if stock_code not in self.companies:
            return None

        company = self.companies[stock_code]
        products_analysis = []

        for product_name in company['products']:
            if product_name in self.products:
                products_analysis.append({
                    'product_name': product_name,
                    **self.products[product_name]
                })

        return {
            'company_name': company['name'],
            'industry': self.name,
            'position': company['position'],
            'chain_flow': self.chain_flow,
            'description': self.description,
            'products': products_analysis,
        }


# ============================================================================
# 产业链知识库
# ============================================================================

def initialize_industry_chains() -> Dict[str, IndustryChain]:
    """初始化产业链知识库"""
    chains = {}

    # ========================================================================
    # 1. 光伏产业链
    # ========================================================================
    photovoltaic = IndustryChain(
        name="光伏设备",
        chain_flow="硅矿 → 工业硅 → 高纯硅料 → 硅片 → 电池片 → 组件 → 光伏电站 → 发电",
        description="光伏发电产业链，从硅料到电站的完整链条"
    )

    # 高纯硅料（核心原料）
    photovoltaic.add_product("高纯硅料", {
        'level': 'A',  # 西红柿
        'level_name': 'A级-核心原料（西红柿）',
        'reason': '光伏组件的核心原材料，无法替代',
        'value_ratio': 0.15,  # 占组件成本15%
        'value_ratio_desc': '占光伏组件总成本约15%',
        'substitutability': 'none',
        'substitutability_desc': '硅基路线无替代品，钙钛矿等新技术尚未成熟',
        'tech_barrier': 'high',
        'tech_barrier_desc': '高纯度要求（9个9以上），技术壁垒高',
        'market_concentration': 'high',
        'market_concentration_desc': '全球前5家占70%+市场份额',
        'importance_score': 95,
        'analogy': '就像西红柿炒鸡蛋里的西红柿，没有就做不出这道菜',
    })

    # 硅片
    photovoltaic.add_product("硅片", {
        'level': 'B',  # 鸡蛋
        'level_name': 'B级-关键部件（鸡蛋）',
        'reason': '电池片的基础材料，重要但有一定可替代性',
        'value_ratio': 0.30,
        'value_ratio_desc': '占电池片成本约30%',
        'substitutability': 'low',
        'substitutability_desc': '薄膜电池可绕过，但效率低，主流还是硅片',
        'tech_barrier': 'medium',
        'tech_barrier_desc': '切片技术要求高，但进入门槛低于硅料',
        'market_concentration': 'high',
        'market_concentration_desc': '隆基、中环等前3家占60%+',
        'importance_score': 80,
        'analogy': '就像鸡蛋，很重要，但理论上可以用其他食材替代',
    })

    # 电池片
    photovoltaic.add_product("电池片", {
        'level': 'B',
        'level_name': 'B级-关键部件（鸡蛋）',
        'reason': '光伏组件的核心发电单元',
        'value_ratio': 0.40,
        'value_ratio_desc': '占组件成本约40%',
        'substitutability': 'low',
        'substitutability_desc': 'PERC、TOPCon、HJT等技术路线，但硅基电池是主流',
        'tech_barrier': 'medium-high',
        'tech_barrier_desc': '转换效率竞争激烈，技术迭代快',
        'market_concentration': 'medium',
        'market_concentration_desc': '前10家占50%+',
        'importance_score': 85,
        'analogy': '就像鸡蛋，是核心食材',
    })

    # 光伏组件
    photovoltaic.add_product("光伏组件", {
        'level': 'C',
        'level_name': 'C级-重要辅料（食用油）',
        'reason': '组装环节，技术壁垒相对较低',
        'value_ratio': 0.60,
        'value_ratio_desc': '占电站成本约60%',
        'substitutability': 'medium',
        'substitutability_desc': '组件厂商众多，可替代性强',
        'tech_barrier': 'low-medium',
        'tech_barrier_desc': '组装技术门槛较低',
        'market_concentration': 'low',
        'market_concentration_desc': '竞争激烈，集中度低',
        'importance_score': 60,
        'analogy': '就像食用油，重要但供应商很多',
    })

    # 添加公司
    photovoltaic.add_company("通威股份", "600438", ["高纯硅料", "电池片"], "上游+中游")
    photovoltaic.add_company("隆基绿能", "601012", ["硅片", "电池片", "光伏组件"], "中游全产业链")
    photovoltaic.add_company("晶澳科技", "002459", ["电池片", "光伏组件"], "中游")
    photovoltaic.add_company("TCL中环", "002129", ["硅片"], "中游")

    chains["光伏设备"] = photovoltaic

    # ========================================================================
    # 2. 白酒产业链
    # ========================================================================
    baijiu = IndustryChain(
        name="白酒",
        chain_flow="原料采购 → 酿造 → 储存/陈化 → 灌装 → 品牌销售 → 终端消费",
        description="中国白酒产业，强调品牌和渠道"
    )

    # 品牌
    baijiu.add_product("白酒品牌", {
        'level': 'A',
        'level_name': 'A级-核心资产（西红柿）',
        'reason': '品牌是白酒的核心价值，消费者认品牌',
        'value_ratio': 0.70,
        'value_ratio_desc': '品牌溢价占终端价格70%+',
        'substitutability': 'none',
        'substitutability_desc': '茅台、五粮液等品牌不可替代',
        'tech_barrier': 'ultra-high',
        'tech_barrier_desc': '需要历史积淀，新品牌难以复制',
        'market_concentration': 'high',
        'market_concentration_desc': '茅台、五粮液占高端市场80%+',
        'importance_score': 98,
        'analogy': '就像西红柿，是这道菜的灵魂',
    })

    # 酿造技术
    baijiu.add_product("酿造工艺", {
        'level': 'B',
        'level_name': 'B级-关键能力（鸡蛋）',
        'reason': '决定酒的品质和口感',
        'value_ratio': 0.20,
        'value_ratio_desc': '影响产品质量，但成本占比不高',
        'substitutability': 'low',
        'substitutability_desc': '各家有独特工艺，但可以学习模仿',
        'tech_barrier': 'high',
        'tech_barrier_desc': '需要长期技术积累',
        'market_concentration': 'medium',
        'market_concentration_desc': '名酒企业各有特色',
        'importance_score': 75,
        'analogy': '就像炒菜的技术，很重要但可以学',
    })

    # 渠道
    baijiu.add_product("销售渠道", {
        'level': 'C',
        'level_name': 'C级-重要辅料（食用油）',
        'reason': '销售渠道重要，但可替代性强',
        'value_ratio': 0.10,
        'value_ratio_desc': '渠道加价约10-15%',
        'substitutability': 'high',
        'substitutability_desc': '线上线下多渠道，可替代',
        'tech_barrier': 'low',
        'tech_barrier_desc': '渠道建设门槛不高',
        'market_concentration': 'low',
        'market_concentration_desc': '渠道分散',
        'importance_score': 50,
        'analogy': '就像食用油，重要但选择很多',
    })

    # 添加公司
    baijiu.add_company("贵州茅台", "600519", ["白酒品牌", "酿造工艺"], "品牌龙头")
    baijiu.add_company("五粮液", "000858", ["白酒品牌", "酿造工艺"], "品牌龙头")
    baijiu.add_company("山西汾酒", "600809", ["白酒品牌", "酿造工艺"], "区域龙头")
    baijiu.add_company("泸州老窖", "000568", ["白酒品牌", "酿造工艺"], "品牌企业")

    chains["白酒"] = baijiu

    # ========================================================================
    # 3. 锂电池产业链
    # ========================================================================
    battery = IndustryChain(
        name="电池",
        chain_flow="锂矿 → 碳酸锂 → 正极材料 → 电芯 → 电池Pack → 新能源车/储能",
        description="锂电池产业链，新能源汽车核心"
    )

    # 碳酸锂
    battery.add_product("碳酸锂", {
        'level': 'A',
        'level_name': 'A级-核心原料（西红柿）',
        'reason': '锂电池的核心原材料，无法替代',
        'value_ratio': 0.40,
        'value_ratio_desc': '占电芯成本40%+（价格高时）',
        'substitutability': 'none',
        'substitutability_desc': '锂电池必须用锂，无替代',
        'tech_barrier': 'medium',
        'tech_barrier_desc': '提取技术成熟，但资源稀缺',
        'market_concentration': 'high',
        'market_concentration_desc': '全球资源集中，前5家占60%+',
        'importance_score': 95,
        'analogy': '就像西红柿，是锂电池的核心',
    })

    # 正极材料
    battery.add_product("正极材料", {
        'level': 'B',
        'level_name': 'B级-关键部件（鸡蛋）',
        'reason': '决定电池性能的关键材料',
        'value_ratio': 0.50,
        'value_ratio_desc': '占电芯成本约50%',
        'substitutability': 'low',
        'substitutability_desc': '三元、磷酸铁锂等路线，有一定替代性',
        'tech_barrier': 'high',
        'tech_barrier_desc': '配方和工艺要求高',
        'market_concentration': 'medium',
        'market_concentration_desc': '前10家占70%+',
        'importance_score': 85,
        'analogy': '就像鸡蛋，是关键食材',
    })

    # 电芯
    battery.add_product("电芯", {
        'level': 'B',
        'level_name': 'B级-关键部件（鸡蛋）',
        'reason': '电池的核心组件',
        'value_ratio': 0.70,
        'value_ratio_desc': '占电池Pack成本约70%',
        'substitutability': 'low',
        'substitutability_desc': '不同厂商产品有差异，但功能相同',
        'tech_barrier': 'high',
        'tech_barrier_desc': '制造工艺复杂，良率要求高',
        'market_concentration': 'high',
        'market_concentration_desc': '宁德时代一家占35%+',
        'importance_score': 90,
        'analogy': '就像鸡蛋，是核心部件',
    })

    # 添加公司
    battery.add_company("宁德时代", "300750", ["电芯"], "中游龙头")
    battery.add_company("比亚迪", "002594", ["正极材料", "电芯"], "垂直整合")
    battery.add_company("赣锋锂业", "002460", ["碳酸锂"], "上游")
    battery.add_company("天齐锂业", "002466", ["碳酸锂"], "上游")

    chains["电池"] = battery

    # ========================================================================
    # 4. 半导体产业链
    # ========================================================================
    semiconductor = IndustryChain(
        name="半导体",
        chain_flow="硅片 → IC设计 → 晶圆制造 → 封装测试 → 芯片应用",
        description="半导体产业链，科技核心"
    )

    # 晶圆制造
    semiconductor.add_product("晶圆制造", {
        'level': 'A',
        'level_name': 'A级-核心环节（西红柿）',
        'reason': '芯片制造的核心环节，技术壁垒最高',
        'value_ratio': 0.50,
        'value_ratio_desc': '占芯片总成本约50%',
        'substitutability': 'none',
        'substitutability_desc': '无法绕过的环节',
        'tech_barrier': 'ultra-high',
        'tech_barrier_desc': '先进制程（7nm以下）只有台积电、三星等少数公司掌握',
        'market_concentration': 'ultra-high',
        'market_concentration_desc': '台积电占全球代工市场60%+',
        'importance_score': 98,
        'analogy': '就像西红柿，是芯片的核心',
    })

    # IC设计
    semiconductor.add_product("IC设计", {
        'level': 'B',
        'level_name': 'B级-关键能力（鸡蛋）',
        'reason': '决定芯片功能和性能',
        'value_ratio': 0.30,
        'value_ratio_desc': '占芯片价值约30%',
        'substitutability': 'low',
        'substitutability_desc': '不同设计公司产品有差异',
        'tech_barrier': 'high',
        'tech_barrier_desc': '需要大量人才和经验积累',
        'market_concentration': 'medium',
        'market_concentration_desc': '高通、联发科等占50%+',
        'importance_score': 80,
        'analogy': '就像配方，决定菜的味道',
    })

    # 封装测试
    semiconductor.add_product("封装测试", {
        'level': 'C',
        'level_name': 'C级-重要辅料（食用油）',
        'reason': '后段工序，技术门槛相对较低',
        'value_ratio': 0.20,
        'value_ratio_desc': '占成本约20%',
        'substitutability': 'medium',
        'substitutability_desc': '封测厂商较多，可替代',
        'tech_barrier': 'medium',
        'tech_barrier_desc': '技术门槛低于设计和制造',
        'market_concentration': 'medium',
        'market_concentration_desc': '前10家占60%+',
        'importance_score': 60,
        'analogy': '就像食用油，重要但选择多',
    })

    # 添加公司
    semiconductor.add_company("中芯国际", "688981", ["晶圆制造"], "制造龙头")
    semiconductor.add_company("华虹半导体", "688347", ["晶圆制造"], "制造企业")
    semiconductor.add_company("长电科技", "600584", ["封装测试"], "封测龙头")

    chains["半导体"] = semiconductor

    return chains


# 全局实例
INDUSTRY_CHAINS = initialize_industry_chains()


def get_industry_chain_analysis(stock_code: str, industry: str) -> Optional[Dict]:
    """
    获取股票的产业链分析

    Args:
        stock_code: 股票代码
        industry: 行业名称

    Returns:
        产业链分析结果，如果没有配置则返回None
    """
    # 先尝试精确匹配
    if industry in INDUSTRY_CHAINS:
        chain = INDUSTRY_CHAINS[industry]
        return chain.get_company_analysis(stock_code)

    # 尝试模糊匹配
    for chain_name, chain in INDUSTRY_CHAINS.items():
        if chain_name in industry or industry in chain_name:
            result = chain.get_company_analysis(stock_code)
            if result:
                return result

    return None


def get_available_industries() -> List[str]:
    """获取已配置的行业列表"""
    return list(INDUSTRY_CHAINS.keys())


def get_available_companies() -> Dict[str, List[str]]:
    """获取已配置的公司列表（按行业分组）"""
    result = {}
    for industry_name, chain in INDUSTRY_CHAINS.items():
        companies = []
        for stock_code, company_info in chain.companies.items():
            companies.append(f"{company_info['name']}({stock_code})")
        result[industry_name] = companies
    return result


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("产业链知识库测试")
    print("=" * 60)

    # 测试通威股份
    print("\n测试1: 通威股份(600438)")
    result = get_industry_chain_analysis("600438", "光伏设备")
    if result:
        print(f"公司: {result['company_name']}")
        print(f"行业: {result['industry']}")
        print(f"产业链位置: {result['position']}")
        print(f"产业链流程: {result['chain_flow']}")
        print(f"\n产品分析:")
        for product in result['products']:
            print(f"  - {product['product_name']}")
            print(f"    等级: {product['level_name']}")
            print(f"    重要性评分: {product['importance_score']}")
            print(f"    类比: {product['analogy']}")

    # 测试山西汾酒
    print("\n" + "=" * 60)
    print("测试2: 山西汾酒(600809)")
    result = get_industry_chain_analysis("600809", "白酒")
    if result:
        print(f"公司: {result['company_name']}")
        print(f"产业链流程: {result['chain_flow']}")
        print(f"\n产品分析:")
        for product in result['products']:
            print(f"  - {product['product_name']}: {product['level_name']}")

    # 显示配置概况
    print("\n" + "=" * 60)
    print("已配置产业链:")
    for industry in get_available_industries():
        print(f"  - {industry}")

    print("\n已配置公司:")
    companies = get_available_companies()
    for industry, company_list in companies.items():
        print(f"  {industry}:")
        for company in company_list:
            print(f"    - {company}")
