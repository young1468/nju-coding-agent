# Order Demo

一个用于演示 Coding Agent 跨文件理解和修复能力的独立 Python 项目。项目没有第三方业务依赖，只有 `pytest` 用于测试。

## 故意保留的问题

- `pricing.py` 将 `Decimal` 转为 `float`，并在税后才应用优惠券。
- `catalog.py` 在确认全部商品有库存前就扣减库存，失败时不会回滚。
- `checkout.py` 和 `cli.py` 依赖上述模块，因此需要在保持 CLI 调用方式兼容的前提下完成修复。

从本目录运行：

```powershell
python -m pytest -q
```

录制演示前可在仓库根目录运行 `python scripts/reset_order_demo.py` 恢复故障基线；脚本只覆盖 `pricing.py` 和 `catalog.py`，预期基线为 `5 failed, 1 passed`。演示完成后请恢复正确实现并确认测试全部通过。

推荐给 Agent 的任务：

```text
修复 order_demo 中所有失败的测试，不要修改测试文件。

要求：
1. 金额计算必须使用 Decimal，最终金额保留两位小数。
2. 优惠券应在计算税费前应用。
3. 库存不足时不得修改任何商品库存。
4. 保持 cli.py 的现有调用方式兼容。
5. 修复后运行完整 pytest，并说明修改的文件和验证结果。
```
