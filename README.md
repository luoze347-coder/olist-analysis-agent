# Olist 电商经营分析助手

输入“2018 年每个月的销售额是多少？”，可以看到月度趋势、逐月金额，以及生成这张图的 SQL。使用的是巴西电商平台 Olist 的历史数据，共 99,441 笔订单、112,650 条商品明细。这里的销售额按已送达订单的商品价格计算，以巴西雷亚尔计价，不含运费。

可以先看随仓库提供的分析示例。在项目根目录运行下面的命令，然后打开 <http://127.0.0.1:8080>。示例读取已导出的统计结果，无需模型密钥。

~~~sh
python -m http.server 8080 --bind 127.0.0.1 --directory docs
~~~

## 本地运行

1. 准备 Python 3.13 环境，运行 `python -m pip install -r requirements.txt`。
2. 从 [Olist 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 下载 ZIP，在项目根目录运行 `python scripts/prepare_data.py --source "下载的 ZIP 文件路径"`。脚本会生成本地 DuckDB 数据库。
3. 在启动终端设置环境变量 `DEEPSEEK_API_KEY`，运行 `python run.py`，打开 <http://127.0.0.1:8000>。

## 查询过程

FastAPI 接收问题，LangChain 调用 DeepSeek 查看数据字典、生成查询。SQLGlot 检查语句和允许访问的表，DuckDB 以只读方式执行。页面同时展示回答和查询结果，方便核对金额、日期范围和统计口径。遇到利润、广告 ROI 等问题时，助手会说明原始订单缺少哪些数据。

[指标定义](app/metrics.py) · [工具调用](app/agent.py) · [SQL 校验](app/sql_guard.py)

## 验证

运行 `python -m pytest -q` 执行测试。准备好数据库后，可用 `python scripts/evaluate.py` 检查基准 SQL，加 `--live` 调用 DeepSeek 做完整在线评测（产生 API 费用）。评测题包括销售、配送和复购，也包括数据不足时应拒答的问题。题目及预期结果见 [评测用例](eval/cases.json)。

一次完整在线评测的结果（2026-11）：30 题严格结果比较通过 28/30——SQL 题 19/20，缺失数据题拒答 9/10；4 项安全探针（写操作、多语句、外部文件、未知表）全部拦截；平均耗时 4.54 s。逐题结果与两道未通过题的原始回答见 [评测报告](docs/eval-report.json)。
