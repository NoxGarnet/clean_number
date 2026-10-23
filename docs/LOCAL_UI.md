# 本地工作台

双击仓库根目录的 **Start-CleanNumber.vbs**。工作台会在默认浏览器中打开，
无需输入命令；重复双击会打开已运行的工作台。

## 第一次使用

1. 选择直接存放 `.xls` / `.xlsx` 的输入文件夹，选择抗压或矩形三点抗折。
2. 点击“检查文件”，核对文件名、龄期、试件及条件分组。存在 `experiment.yaml`
   时载入该配置；也可以选择本地 YAML 或已保存的预设。
3. 在表单中调整名称、分组标签、计算区间与抗折几何尺寸，按需保存预设。
4. 选择结果存放目录，点击“开始处理”。每次生成一个新的运行子目录。
5. 查看逐文件结果、失败记录、图表及可下载文件，或打开结果文件夹。

“体验合成示例”载入仓库自带的解析曲线，不读取私人项目。
表单之外的配置字段会保留。支持的输入列、单位和方法沿用 [支持矩阵](../SUPPORT_MATRIX.md)；
界面不增加任意单位换算或新的试验方法。峰值比例区间为现有诊断模量的计算设置。

## 运行环境

界面和本地服务不需要额外依赖；使用核心 `requirements.txt` 中的包。
首次使用需先在源码目录创建 `.venv` 并安装核心依赖。PowerShell 命令如下，无需激活环境：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

完成后双击 `Start-CleanNumber.vbs`。启动器依次检查显式指定的解释器、源码目录的
`.venv`、系统 Python，选择具备核心依赖的环境；不会自动安装依赖或查找私人工作区。

需要指定解释器时：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-CleanNumber.ps1 -Python <python.exe完整路径>
```

直接调试服务：

```powershell
python local_ui.py
```

## 记录与关闭

配置预设、运行记录、日志及默认输出位于 Git 忽略的 `.local-ui/`，含本机路径和可能的实验信息，
不进入公开源码。原始配置及原始数据保持不变；实际使用的配置副本随本次输出保存。
后台调用现有 `analyze.py --phase2-only`，生成表格与图表；可选 Word/PDF 不在本版界面范围内。

浏览器关闭后服务仍在本机运行，以便继续处理和重开查看。
运行 `Stop-CleanNumber.ps1` 可关闭服务及尚在处理的任务，部分输出保留。
也可在界面停止当前任务。下次启动时，未正常收尾的历史任务显示为“已中断”。

服务只绑定 `127.0.0.1`，不连接外部服务，不需要账号。操作请求校验本地来源和临时会话令牌。
