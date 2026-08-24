# CHANGELOG (更新日志)

## [v4.0.1] - 2026-08-24
### 🎨 产品级 UX 体验优化 (Progressive Disclosure)
- **JSON Log Schema HTML 折叠包裹**：在 `index-prediction` 技能及主文档中，将标准 JSON 日志块放入 `<details><summary>📄 点击展开量化结构日志 (Prediction Log Schema)</summary> ... </details>` 折叠标签中。
- 效果：普通人在网页/IDE阅读时报告干净顺畅；Python/Dify 自动化程序依然能正常解析读取。

---

## [v4.0.0] - 2026-08-24
### 🏆 A股指数量化概率预测模型 v1.0 发布 (Major Release)
- **正式引入“三阶段闭环架构”**：`08:30 先验预测` $\rightarrow$ `09:25 竞价验证与概率更新` $\rightarrow$ `15:00 结果验证与 Brier Score 统计`。
- **四大执行指令**：正式支持 `“开始盘前推演”`、`“执行竞价验证”`、`“记录今日结果”`、`“查看预测统计”`。
- **二十六条终极纪律**：严格隔离未来数据，引入非严格回测模式标记，规定竞价放量基准比率，并统一输出可解析的 `Prediction Log` JSON Schema。
