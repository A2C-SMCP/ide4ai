# UAT 报告模板

每个场景完成后必须把下面的报告保存为清单中的 `<artifacts_dir>/report.md`。证据列使用当前场景契约规定的截图文件名，且截图必须与报告位于同一个 `artifacts_dir`；不能只在对话中输出报告。

```markdown
## ide4ai UAT

- 结论：PASS | FAIL | FLAKY | BLOCKED
- 场景：<manifest.scenario>
- Inspector：@modelcontextprotocol/inspector@2.4.0
- 被测版本：<git commit + dirty/clean>
- 运行目录：<absolute run_dir>

### 检查点

| 检查点 | 结果 | 证据 |
|---|---|---|
| <场景检查点 1> | PASS/FAIL/NOT RUN | <截图或 Inspector 调用结果摘要> |
| <场景检查点 2> | PASS/FAIL/NOT RUN | <截图或 Inspector 调用结果摘要> |

### 偏差与诊断

- 首次失败：<无或原始错误>
- 隔离复跑：<未执行/结果>
- 分类：产品失败/框架失败/选择器漂移/无
- 备注：<必要的 UI 兼容性或环境说明>
```

报告只陈述已观察到的结果。未执行的检查点写 `NOT RUN`，不能根据单元测试或源码推断为通过。一个运行目录只保存其 manifest 所选场景的报告和证据。
