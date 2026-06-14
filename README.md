# Amazon Product Lab MVP

把人工整理后的亚马逊商机数据转换为可审计的候选评分、三情景利润和决策报告。

## 当前能力

- 读取标准 CSV 并校验必填字段
- 计算乐观、基准、悲观三种利润情景
- 按需求、竞争、差异化、经济性、供应链和运营能力评分
- 对高合规风险、高侵权风险、危险品和低利润候选执行红线拦截
- 输出排序后的 `report.json` 和 `report.md`

当前不连接亚马逊后台，也不执行采购、上架、调价或广告操作。

## 商机探测器原始导出

可直接输入亚马逊美国站商机探测器下载的中文 CSV：

```bash
python3 -m amazon_product_lab "/Users/wangzhi/Downloads/细分市场搜索结果_2026_6_14.csv" --output-dir output
```

程序会自动识别原始导出并生成：

- `output/market_report.md`：需求侧 Top 50 初筛报告
- `output/market_report.json`：全部市场、原始指标、分项得分和来源哈希
- `output/candidate_enrichment.csv`：Top 30 待补充成本、广告、供应链和风险数据的模板

需求侧初筛不包含利润、合规和侵权结论，不能直接作为打样或采购决定。补齐
`candidate_enrichment.csv` 的空字段后，再将它作为输入运行，生成正式利润与风险报告。

## 运行

需要 Python 3.10 以上，无第三方依赖。

```bash
cd /Users/wangzhi/Documents/amzon_project/amazon-product-lab
python3 -m amazon_product_lab examples/candidates.csv --output-dir output
```

输出：

```text
output/report.json
output/report.md
```

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

## 输入口径

复制 `examples/candidates.csv` 作为模板。字段中的比率使用小数，例如 `15%` 写作 `0.15`。

| 字段 | 含义 |
|---|---|
| `opportunity_id` | 自定义机会编号 |
| `marketplace` | 首期固定为 `US` |
| `niche` | 商机探测器细分市场名称 |
| `sale_price` | 预计销售价 |
| `landed_cost` | 含采购、头程、关税的到岸成本 |
| `fba_fee` | 每单 FBA 配送费 |
| `referral_fee_rate` | 亚马逊销售佣金率 |
| `storage_cost` | 每件预计仓储成本 |
| `return_rate` | 预计退货率 |
| `return_loss_rate` | 每次退货损失占售价比例 |
| `conversion_rate` | 预计购买转化率 |
| `cpc` | 预计广告单次点击费用 |
| `*_score` | 人工按证据填写的 0 至 100 分子项 |
| `compliance_risk` | `low`、`medium` 或 `high` |
| `ip_risk` | `low`、`medium` 或 `high` |
| `hazmat` | 是否危险品，`true` 或 `false` |
| `seasonal` | 是否季节性商品，`true` 或 `false` |

广告获客成本按 `CPC / 转化率` 计算。经济性得分由基准贡献利润率确定，不由人工填写。

## 第一周操作

1. 从美国站商机探测器选取 20 至 30 个细分市场。
2. 将后台数据和供应商报价整理到模板中。
3. 根据搜索趋势、品牌集中度、评论痛点等证据填写五个非财务评分。
4. 运行分析器，优先人工复核 `sample` 候选。
5. 将误判原因记入实验日志，暂不立即修改权重。

下一阶段再加入商机探测器原始导出字段映射、评论聚类和实验结果回传。
