# ProcessingJob 设计

ProcessingJob 用于记录一次文档处理任务的状态，包括 queued、processing、retrying、succeeded 和 failed。它让 worker 执行链路、失败重试和任务排查都能落到独立对象上。

# 来源引用

PureLink 的回答会返回 citations，说明答案来自哪个文件和哪个 chunk。这样做的目标不是让大模型“看起来像有来源”，而是让来源能够真实追踪到后端检索结果。
