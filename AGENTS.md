# Project Instructions

回复使用中文，保持简洁并优先直接执行。

## Project Goal

这是一个亚马逊 AI 选品实验室。第一阶段服务自有美国站店铺，通过真实销售反馈建立可复盘、可迭代的选品机制。

## Current Scope

- 人工导入商机探测器及供应链数据
- 确定性利润计算、评分和风险红线
- 输出候选排序及决策报告
- 人工决定打样、采购、上架和运营动作

暂不做后台爬虫、自动采购、自动上架、自动调价和自动广告投放。

## Tech Stack

- Python 3.10+
- 仅使用标准库
- 测试使用 `unittest`

## Commands

- 测试：`python3 -m unittest discover -s tests -v`
- 示例：`python3 -m amazon_product_lab examples/candidates.csv --output-dir output`
- 编译检查：`python3 -m compileall -q amazon_product_lab`

## Engineering Rules

- 财务和评分使用确定性公式，LLM 只用于文本洞察。
- 所有建议必须保留输入数据、计算结果和否决理由。
- 缺失字段应明确报错，不得猜测或补造。
- 合规、侵权、危险品和利润红线优先于总分。
- 修改行为前先写失败测试，完成后运行完整测试。
- 不引入第三方依赖，除非用户明确批准。

## Context

新会话先阅读：

1. `docs/HANDOFF.md`
2. `docs/EXECUTION_PLAN.md`
3. `README.md`

