# AI 税务会计 Agent 系统

基于 Anthropic Claude SDK 构建的多 Agent 税务分析系统，帮助会计师自动处理税务文件、回答税法问题、检测异常交易、生成分析报告。

## 系统架构

```
用户输入（文件 or 问题）
        ↓
   Router Agent（判断任务类型）
   ↙        ↓        ↘        ↘
文档处理   税法问答   异常检测   报告生成
Agent     Agent     Agent     Agent
        ↓
   最终输出（结构化 JSON / Markdown 报告）
```

每个 Agent 都实现了完整的 Anthropic **tool-use agentic loop**：
1. 向 Claude 发送请求（含工具定义）
2. Claude 返回 `tool_use` 调用
3. 执行本地工具，将结果以 `tool_result` 返回
4. 重复直到 Claude 返回 `end_turn`
5. 最终报告支持流式输出

## 项目结构

```
tax-agent/
├── main.py                    # CLI 入口，支持 5 种运行模式
├── router.py                  # 任务路由 Agent
├── prompts.py                 # 所有 System Prompt 集中管理
├── .env.example               # 环境变量模板
├── requirements.txt
├── README.md
├── agents/
│   ├── base_agent.py          # 基类（tool-use 循环、流式输出）
│   ├── document_agent.py      # 文档处理（OCR + 字段提取）
│   ├── research_agent.py      # 税法研究（问答 + 引用来源）
│   ├── anomaly_agent.py       # 异常检测（规则 + AI 双重）
│   └── report_agent.py        # 报告生成（流式 Markdown）
├── tools/
│   ├── ocr_tool.py            # PDF/图片文字提取
│   ├── data_parser.py         # 税务字段结构化解析
│   ├── anomaly_detector.py    # 规则 + AI 异常检测引擎
│   └── report_formatter.py    # 报告格式化（Markdown/JSON）
└── knowledge/
    └── tax_guidelines.md      # 内置税法知识库（22 条 Q&A）
```

## 安装

### 1. 克隆/下载项目

```bash
cd tax-agent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **注意**：`pytesseract` 需要额外安装 [Tesseract OCR 引擎](https://github.com/tesseract-ocr/tesseract)（仅处理图片时需要）。使用 `--mock` 模式不需要安装 Tesseract。

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 Anthropic API Key
```

`.env` 内容：
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 使用方式

### 模式 1：处理税务文件（W-2 / 1099 / 发票）

```bash
python main.py --file w2_sample.pdf
```

**输出示例**：
```
[Router] 识别任务类型: document_processing

[DocumentAgent] 开始处理文件: w2_sample.pdf
[DocumentAgent] 调用工具: extract_document_text({"file_path": "w2_sample.pdf"})
[DocumentAgent] 调用工具: parse_document_fields({"raw_text": "..."})
[DocumentAgent] 提取完成 ✓ | 文件类型: W-2 | 收入: $120,000.00 | 置信度: high

提取结果：
{
  "document_type": "W-2",
  "taxpayer_name": "Jane Doe",
  "employer_name": "Anthropic Inc",
  "income_amount": "$120,000.00",
  "tax_withheld_federal": "$24,000.00",
  "tax_withheld_state": "$7,200.00",
  "period": "2024",
  "confidence": "high"
}
```

---

### 模式 2：税法问答

```bash
python main.py --ask "我的家庭办公室可以抵扣多少税？"
python main.py --ask "What is the 2024 standard deduction amount?"
```

**输出示例**：
```
[Router] 识别任务类型: research

[ResearchAgent] 接收到问题: 我的家庭办公室可以抵扣多少税？
[ResearchAgent] 调用工具: search_tax_guidelines({"query": "家庭办公室"})
[ResearchAgent] 调用工具: format_tax_answer(...)
[ResearchAgent] 回答完成 ✓ | 引用 3 条法律依据

根据 IRC Section 280A 及 IRS Publication 587，家庭办公室抵扣须满足专用性要求...

法律依据：
  • IRC § 280A
  • IRS Publication 587
  • Form 8829
```

---

### 模式 3：检测异常交易

```bash
python main.py --transactions transactions.csv
```

CSV 格式要求（支持中英文列名）：

| date | vendor | amount | invoice_number | description | payment_method |
|------|--------|--------|----------------|-------------|----------------|
| 2024-01-15 | Office Depot | 500.00 | INV-001 | 办公用品 | corporate_card |

**输出示例**：
```
[AnomalyAgent] 加载交易数据: transactions.csv
[AnomalyAgent] 正在执行规则检测...
[AnomalyAgent] 检测完成 ✓ | 共 4 条异常 | 高风险 2 | 中风险 1 | 低风险 1

异常检测结果：
  总计: 4 条异常
  ⚠️  高风险: 2
  🔶 中风险: 1
  🔷 低风险: 1

异常详情：
  ⚠️  第2行 | duplicate_payment | 疑似重复付款：Office Depot，$500.00，相差1天
  ⚠️  第7行 | statistical_outlier | 金额 $98,000.00 超过统计阈值
  🔶 第5行 | missing_fields | 缺少：供应商名称, 发票号
```

---

### 模式 4：生成完整报告

```bash
# 同时处理文件和交易数据
python main.py --report --file w2.pdf --transactions data.csv

# 只生成报告（无文件）
python main.py --report --ask "有哪些常见的税务优化策略？"
```

---

### 模式 5：Mock 测试全流程（推荐入门）

```bash
python main.py --mock --report
```

使用内置 Mock 数据（无需真实文件）：
- **Mock W-2**：Anthropic Inc, Jane Doe, 收入 $120,000.00
- **Mock 交易数据**：10 条，含 4 类注入异常

**完整输出示例**：
```
[Router] 识别任务类型: report（Mock 全流程）

[DocumentAgent] 开始处理文件: mock
[DocumentAgent] 提取完成 ✓ | 文件类型: W-2 | 收入: $120,000.00

[AnomalyAgent] 加载交易数据: mock
[AnomalyAgent] 检测完成 ✓ | 共 4 条异常 | 高风险 2 | 中风险 1 | 低风险 1

[ReportAgent] 开始生成分析报告...
[ReportAgent] 正在输出报告...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 税务文件分析报告
> 生成时间：2024年12月01日 14:30

## 一、执行摘要
- 成功提取 W-2（Anthropic Inc，2024）：收入 $120,000.00，联邦税代扣 $24,000.00
- ⚠️ 检测到 2 条高风险异常交易，需立即人工复查...
...
```

---

### 模式 6：交互式模式

```bash
python main.py
```

进入 REPL 模式，可直接输入问题或文件路径。

---

## Agent 说明

| Agent | 文件 | 功能 | 使用工具 |
|-------|------|------|---------|
| Router | `router.py` | 任务分类路由 | `classify_task` |
| DocumentAgent | `agents/document_agent.py` | 提取税务文件字段 | `extract_document_text`, `parse_document_fields` |
| ResearchAgent | `agents/research_agent.py` | 税法问答+引用 | `search_tax_guidelines`, `format_tax_answer` |
| AnomalyAgent | `agents/anomaly_agent.py` | 交易异常检测 | `load_transactions`, `run_rule_checks`, `run_ai_checks`, `summarize_anomalies` |
| ReportAgent | `agents/report_agent.py` | 生成分析报告 | `compile_report_data`, `generate_executive_summary`, `format_final_report` |

## 异常检测规则

| 规则 | 描述 | 风险等级 |
|------|------|---------|
| `duplicate_payment` | 相同金额+供应商+7天内重复 | 高 |
| `statistical_outlier` | 金额超过均值+3σ | 高 |
| `missing_fields` | 缺少发票号或供应商 | 中 |
| `round_number` | 整数金额 ≥ $1,000.00 | 低 |
| `ai_flagged` | AI 识别的其他异常 | 中 |

## 知识库

`knowledge/tax_guidelines.md` 内置 22 条税务 Q&A，涵盖：
家庭办公室抵扣、标准扣除、Section 179、里程率、子女税收抵免、自雇税、401(k)、资本利得、折旧、教育抵免、HSA、出租房、海外收入、预缴税款、餐饮娱乐、Section 199A、赌博损失、慈善捐款、医疗费用、商业用车、NOL、遗产赠与税。

## 技术栈

- **Python 3.11+**
- **anthropic SDK** — Claude claude-sonnet-4-20250514
- **pypdf** — PDF 文字提取
- **pytesseract + Pillow** — 图片 OCR
- **pandas** — CSV 数据处理
- **python-dotenv** — 环境变量管理

## 免责声明

本系统由 AI 自动生成分析结果，仅供会计师参考。所有税务相关决策请以最新 IRS 官方指引为准，并在必要时咨询持证税务专业人士（CPA / EA / Tax Attorney）。
