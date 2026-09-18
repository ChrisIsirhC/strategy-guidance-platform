"""Build a source-faithful field catalog from the strategy text package.

This is a discovery layer only: it preserves the original text in contextual
excerpts and never labels a view as bullish, bearish, or otherwise summarizes it.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "site" / "site-data.json"
OUTPUT_JSON = ROOT / "data" / "strategy_field_catalog.json"
OUTPUT_CSV = ROOT / "data" / "strategy_field_catalog.csv"

# Candidate fields are deliberately grouped by data family, rather than by a
# judgement on the original text. Aliases are only used for retrieval/counting.
FIELD_DEFINITIONS = {
    "利率与债券": {
        "债券品种": ["地方债", "国债", "政金债", "信用债", "存单", "同业存单"],
        "期限": ["久期", r"\d+(?:\.\d+)?年", "短端", "中端", "长端", "超长端"],
        "到期收益率": ["收益率", "YTM", "到期收益率"],
        "收益率变动": ["bp", "BP", "上行", "下行"],
        "曲线与斜率": ["曲线", "陡峭", "平坦", "期限利差"],
        "信用利差": ["信用利差", "利差", "等级利差", "条款利差"],
        "资金利率": ["DR007", "DR001", "R007", "资金利率", "回购利率"],
        "杠杆": ["杠杆"],
        "一级发行": ["一级发行", "发行规模", "发行利率", "认购倍数", "供给"],
        "机构需求": ["保险", "银行", "基金需求", "配置盘", "大行"],
        "流动性与仓位": ["流动性", "仓位", "建仓", "减仓", "止盈", "加仓"],
    },
    "宏观与海外": {
        "CPI": ["CPI"], "PPI": ["PPI"], "GDP": ["GDP"], "PMI": ["PMI"],
        "通胀与实际利率": ["通胀", "实际利率", "通胀预期"],
        "美联储与FOMC": ["美联储", "FOMC", "降息", "加息"],
        "就业数据": ["非农", "失业率", "就业"],
        "美元与汇率": ["美元", "汇率", "美元指数"],
        "地缘事件": ["地缘", "关税", "制裁", "冲突", "霍尔木兹"],
    },
    "权益与基金": {
        "指数与点位": ["上证指数", "沪深300", "创业板", "科创", "中证", "指数点位"],
        "涨跌幅": ["上涨", "下跌", "涨幅", "跌幅", "回撤"],
        "成交额与成交量": ["成交额", "成交量", "万亿"],
        "行业与板块": ["板块", "行业", "半导体", "机器人", "医药", "券商"],
        "ETF名称与代码": ["ETF", r"(?<!\d)\d{6}(?!\d)"],
        "基金规模": ["基金规模", "规模"],
        "估值": ["PE", "PB", "估值"],
        "盈利与业绩": ["盈利", "营收", "净利润", "业绩", "基本面"],
        "风格与风险偏好": ["风格", "轮动", "风险偏好", "成长", "红利"],
        "资金流向": ["资金流", "北向", "南向", "申购", "赎回"],
    },
    "商品": {
        "黄金价格": ["黄金", "金价"], "白银价格": ["白银"], "原油价格": ["原油", "油价"],
        "供给与需求": ["供给", "需求", "库存", "产量"],
        "运价与航运": ["运价", "船价", "航运"], "OPEC+": ["OPEC"],
        "避险情绪": ["避险", "风险事件"],
    },
    "REITs": {
        "REITs名称": ["REITs", "REIT"], "资产类型": ["保障房", "仓储", "园区", "高速", "能源"],
        "NAV与估值": ["NAV", "估值", "折价", "溢价"], "分派率": ["分派率", "分红"],
        "运营指标": ["租金", "出租率", "现金流", "融资成本"],
    },
    "转债、衍生品与ABS": {
        "转债价格": ["转债价格", "转债"], "转股溢价率": ["转股溢价率", "溢价率"],
        "正股表现": ["正股"], "波动率": ["波动率", "隐含波动率"],
        "期货基差与持仓": ["基差", "持仓量", "国债期货"],
        "资产池与逾期": ["资产池", "逾期率", "不良率"],
        "增信与分层": ["增信", "分层", "评级", "票息"],
    },
}


def compile_pattern(aliases: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{alias})" for alias in aliases), re.IGNORECASE)


def contextual_excerpt(text: str, match: re.Match[str], radius: int = 72) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    # Re-find against normalized text so positions remain valid after whitespace cleanup.
    start = max(0, match.start() - radius)
    end = min(len(normalized), match.end() + radius)
    return f"{'…' if start else ''}{normalized[start:end]}{'…' if end < len(normalized) else ''}"


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = []
    for category, fields in FIELD_DEFINITIONS.items():
        for field, aliases in fields.items():
            pattern = compile_pattern(aliases)
            occurrences = 0
            strategies: set[str] = set()
            dates: set[str] = set()
            examples: list[dict[str, str]] = []
            for document in data["documents"]:
                for entry in document["entries"]:
                    for cell in entry["cells"]:
                        if "投资经理" in str(cell.get("sourceLabel", "")):
                            continue
                        text = str(cell.get("text", ""))
                        normalized = re.sub(r"\s+", " ", text).strip()
                        matches = list(pattern.finditer(normalized))
                        if not matches:
                            continue
                        occurrences += len(matches)
                        strategies.add(entry["strategy"])
                        dates.add(document["date"])
                        if len(examples) < 3:
                            examples.append({
                                "date": document["date"],
                                "strategy": entry["strategy"],
                                "sourceLabel": str(cell.get("sourceLabel", "")),
                                "excerpt": contextual_excerpt(normalized, matches[0]),
                            })
            if occurrences:
                records.append({
                    "category": category,
                    "field": field,
                    "aliases": aliases,
                    "occurrences": occurrences,
                    "strategyCount": len(strategies),
                    "strategies": sorted(strategies),
                    "dateCount": len(dates),
                    "exampleOccurrences": examples,
                })

    records.sort(key=lambda row: (str(row["category"]), -int(row["occurrences"]), str(row["field"])))
    payload = {
        "generatedAt": data.get("generatedAt"),
        "source": "site/site-data.json; strategy view text only",
        "method": "Rule-based candidate-field scan. Counts are mention counts, not normalized market observations.",
        "fieldCount": len(records),
        "fields": records,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "field", "occurrences", "strategyCount", "dateCount", "strategies", "exampleDate", "exampleStrategy", "exampleExcerpt"])
        writer.writeheader()
        for record in records:
            example = record["exampleOccurrences"][0] if record["exampleOccurrences"] else {}
            writer.writerow({
                "category": record["category"], "field": record["field"], "occurrences": record["occurrences"],
                "strategyCount": record["strategyCount"], "dateCount": record["dateCount"],
                "strategies": "、".join(record["strategies"]), "exampleDate": example.get("date", ""),
                "exampleStrategy": example.get("strategy", ""), "exampleExcerpt": example.get("excerpt", ""),
            })
    print(f"Wrote {len(records)} fields to {OUTPUT_JSON} and {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
