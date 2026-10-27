# Accnary 本轮实际修改与验证

日期：2026-10-25。目标是独立验收及本地按需使用；不更换 KDBX 引擎、不切换加密策略，不发布。

## 实际修改

| 范围 | 改动 | 风险控制 |
|---|---|---|
| 存储 | 同目录独立加密暂存、进程写锁、保存前后摘要、完整 XML/附件比较、快照暂存替换、恢复后校验 | 保留原格式与 PyKeePass；真实双进程/终止/占用和故障注入回归 |
| 会话 | 清空 catalog、registry、索引、UI 值和主密码控件；条件清理剪贴板 | 明示 Python 内存清除限制 |
| 编辑 | 保留 UUID 和隐藏元数据、修正平台类型、注册身份延迟提交、失败命令回滚 | 全字段软件账户、取消、保存失败后再次保存回归 |
| 运行机制 | 完整移除 QSystemTrayIcon、隐藏到托盘、HotkeyFilter、RegisterHotKey 及设置项 | 保留普通最小化、Ctrl+F/N/E/L、空闲锁定、会话锁定/休眠监听；退出停止计时器与监听 |
| 退出 | 检查模型未保存状态、尝试保存；失败可取消退出或明确放弃 | 测试失败取消后窗口仍存活、旧磁盘内容完好 |
| 界面 | 主操作突出、合并分类、平台标识和账号摘要、扩大字号、统一间距、普通录入六项、固定保存栏、详情比例稳定、收藏入口、本地时间 | 使用既有 Qt Widgets 与本地图标，不引入 WebView、动画框架、浏览器监测或联网 |
| 搜索 | 长网址按站点域名定位；支持原始片段、父子域名、编码重定向中的 URL | 不联网；邮箱保持原语义；不把包含共同字符串的恶意后缀域名当作同站点 |
| 备份 UI | 接通原先已有的导出/恢复服务；备份密码验证、明确目标确认、恢复前快照 | 只操作用户选择的文件，本轮全部为隔离虚构库 |
| 工程 | 补充忽略规则、修正图标定位与资源收集、隔离测试 INI、统一版本元数据、更新说明 | 不初始化 Git；保留 Zcode 的构建脚本，不运行其自动覆盖 release 路径 |

## 自动化结果

- 原始完整基线：128 passed，日志 `../audit/evidence/baseline.txt`、`baseline.xml`。
- 首批缺陷复现：18 failed、3 passed，日志 `regressions-before.txt/xml`；这是修复前证据，不是最终失败。
- 最终完整回归：**172 passed，0 failures/errors/skips**；`../audit/evidence/acceptance-summary.json` 与 `acceptance/` 下所有逐模块文本和 JUnit。
- 组成：Phase 0=16，Phase 1=63，Phase 2=26，Phase 3=20，Phase 4=3，独立新增=44。
- 19 个锁定依赖本次 pip-audit 未检出已知漏洞；完整 JSON `pip-audit.json`。
- Windows 会话锁定与休眠通过真实 HWND 注册及模拟消息路由验证；没有真的锁定或休眠用户电脑。

## 真实桌面验证

使用隔离设置与虚构 KDBX，实际操作源码版及独立单文件 EXE。EXE 中完成：解锁 → 粘贴长网址检索 → 修改复杂账号用户名并保存 → 新建普通网站账号 → 导出加密备份 → 输入备份主密码并确认恢复 → 删除该网站账号 → 从回收站恢复 → 普通最小化并恢复 → 复制 → 锁定 → 重新输入主密码 → 点击右上角关闭。

磁盘重新解密核对了 7 个账户、复杂账号 2 种登录方式/3 个绑定、许可证、GUI 新增账号密码和恢复前快照；全部测试 KDBX/备份中没有植入的明文标记。见 `gui-data-verification.json`。关闭后的同路径 EXE 进程检查见 `exit-process-check.json`。

UIA 对 Qt 模态窗口的索引不稳定；实际验证改用工具提供的模态截图区域及可见坐标，没有借此修改应用内部数据来冒充点击成功。测试夹具用于预置展示数据，新增/编辑/备份/回收站操作仍由实际界面完成。

截图位于 `../audit/evidence/screenshots/`：

- `01-baseline-unlock.png`：原界面基线。
- `04-showcase-light.png`：改版后的记录列表与 QQ 账号。
- `05-complex-search.png`：域名命中的复杂软件账号，微信/QQ/手机/邮箱及许可证。
- `06-dark.png`、`07-locked.png`：深色与锁定状态。
- `08-exe-long-url.png`：EXE 粘贴长网址后的命中。
- `09-exe-editor.png`、`10-exe-final.png`：EXE 编辑器和最终主窗口。

进程级缩放渲染与系统缩放必须区分：没有修改 Windows 显示设置。早期 offscreen 渲染字体不可用，未据此判定通过；随后使用 Windows Qt 后端的隐藏测试窗口取得真实字体及 DPR 记录。高缩放/小窗口允许滚动和工具栏溢出菜单，并不等于多显示器热切换已验收。

## 独立构建

固定 `Accnary.spec`，仅指定 `--distpath audit/validation/dist --workpath audit/validation/build`，未调用会覆盖 release 的常规发布脚本。

首轮构建因 Codex 文档运行时 PATH 混入 ICU/UCRT，EXE 达 60,772,319 字节。检查实际 DLL 导入及系统组件后，在 spec 中只排除该工具运行时的 PATH 路径；没有按体积盲删 Qt 必需依赖。最终 EXE：

- **46,070,132 字节，43.94 MiB**；对照交付版 44,767,424 字节，增长约 1.24 MiB，主要是补入此前缺失的现有 PNG 图标及功能代码。
- SHA-256：`83dc5d49a8d7720d7b644277a6e1bf12bd8ceef46443041c811f63211de60775`。
- 打包自检通过；真实主窗口及上述交互通过。
- EXE 与校验文件在 `../audit/validation/dist/`，日志 `build-final.txt`、`exe-check.json`、`exe-artifact.json`。
- 原 release 的隔离构建前后校验一致，见 `release-preservation.json`。

## 尚未解决与后续

详见 CODEX_AUDIT 的残余风险。特别是外部不合作写入窗口、任意同版本未知枚举/Binding 扩展、物理断电和 Python 内存，不作生产安全保证。大库同步保存阻塞是本节原始验收时的状态，已在下方 2026-10-26 更新中处理。

本节记录截至 2026-10-25 的阶段状态；2026-10-26 更新中已完成定向后台存储优化并更新正式 release。

## 收尾复核（2026-10-25）

最终测试 EXE 关闭后再次启动，重新要求主密码；解锁后仍为 7 个平台、7 个测试账户，随后关闭，进程数为 0（`exit-process-check.json`）。Windows Qt 后端分别记录实际 DPR=1.5 与 DPR=2.0；DPR=2.0 的 900×500 主窗口与编辑器截图保存在 evidence/screenshots，没有修改系统缩放。

全量 172 项通过后，仅新增测试设置隔离 fixture；相关 13 项再测通过（`settings-final.txt/xml`）。源码 AST 解析 83 个 Python 文件通过，无编译缓存输出。

临时虚构密码库、独立 INI、构建中间目录与四个临时验收脚本已清理，验证产生的 `__pycache__` 已清理（`cleanup.json`）；基线源码压缩留档、回归测试、日志、截图及独立 EXE 保留。源码差异文件明确排除了并行修改的 `build_exe.py/bat`。本次隔离构建前后 release 文件哈希再次比对一致。

## 后续收敛（2026-10-26）

- 性能证据确认 500 条库保存约 0.98 秒，其中 Argon2 两次派生约 0.60 秒、临时库重开验证约 0.36 秒；保留 KDBX 安全检查，没有降低 KDF 参数。
- 新增 `app/ui/storage_task.py`，并接入解锁/创建、保存、主密码修改、备份导出/恢复及保存后的重读。单一工作线程串行操作 KDBX；应用模态进度页阻止并发 UI 修改，空闲锁定计时暂停，锁定/退出请求延后；错误类型保留，异常回溯清理。
- 新增 `tests/audit/test_storage_task.py` 3 项回归。Pex 自动调度 32 个独立模块，**223 passed，0 failed/errors/skipped**。逐模块结果：`stability-acceptance-20261025/pytest-results-background-storage-20261025.txt`。
- 100 条虚构账户实际后台保存 0.729 秒，最大 Qt 事件间隔 16 毫秒；2000 条保存 1.675 秒，最大间隔 23 毫秒，重新打开均核对账户数完整。
- 修改主密码对话框的真实 Qt 操作已用虚构库验证：新密码重新打开成功，旧密码被拒绝，账户内容保持完整。
- Windows 共享句柄实验表明，允许 `FILE_SHARE_DELETE` 才能保持现有原子替换；该设置仍允许外部客户端通过 `ReplaceFileW` 替换目标。故没有加入假性跨软件锁，最后检查竞态 P0 仍未消除，使用时仍须避免两个可写客户端同时打开同一 KDBX。
- 固定 `build_exe.py --validate-only` 生成隔离 EXE，`--check`、`--smoke`、UIA 窗口启动检查通过；随后 `--promote` 更新 `release/Accnary.exe` 和 SHA sidecar。新文件 46,104,963 字节，SHA-256 为 `0af28e3d6da7e0b1f1631ae7929c8711f2d974f793e83760bbf7c1aa27c94637`。构建、缓存及 Pex 临时 runner 已清理，`release/data` 和用户密码库未触碰。

## 搜索刷新优化（2026-10-26）

- `main_window.py` 保持搜索输入即响应；搜索变化不再重建不变的分类计数导航，显式目录刷新仍更新导航。首轮延迟搜索导致 3 项即时交互断言失败，已撤销延迟方案并通过全量回归。
- 搜索最多显示前 50 条；检测到第 51 条匹配时显示“50+ 个结果”，提示用户继续缩小查询，避免把截断数量当成总数。
- 账户列表在清空和重建期间统一暂停绘制，并通过 `finally` 恢复绘制状态。分类导航改为在启动、库数据变化、恢复、冲突重载和解锁后更新。
- `search_service.py` 为身份 UUID 建立一次性字典索引，避免每个绑定引用反复线性扫描身份列表；使用 `setdefault` 保持原来首条匹配语义。
- 修复后全量回归通过：32 模块、223 passed、0 failed/errors/skipped；首轮失败结果与最终结果分别保存于 `stability-acceptance-20261026/pytest-results-ui-search-first-run-20261026.txt` 和 `pytest-results-full-20261026.txt`。
- 固定 `build_exe.py --validate-only` 与 `--promote` 成功，真实窗口 smoke 和 release EXE 的 `--check` 通过。EXE 46,103,662 字节，SHA-256 为 `a0755af21d54a76ed44e0e958ec6814b0823698ec8a10635983cf6d46ae9e668`，sidecar 匹配。
- 真实大库列表刷新耗时尚待测量。`dist`、`build`、缓存、测试临时目录和构建生成的 `assets/app-icon.ico` 已清理，没有触碰密码库数据。

## 2026-10-26 迭代修复补充

- 搜索：修复域名相关分数压过网址路径分数的问题；父域名/路径查询现在优先命中包含该路径的站点。`tests/audit/test_url_search.py` 修复前失败、修复后 8/8。
- 详情滚动：复杂账户截图复现 `QScrollArea` 内容子卡片被压缩到视口高度。外层 `QHBoxLayout` 增加 `SetMinimumSize` 约束后，长详情产生实际滚动条，卡片高度不低于最小高度。见 `tests/audit/test_iteration_polish.py::test_long_account_details_scroll_without_compressing_sections`。
- 凭据交互：许可证密钥现在可明确显示/隐藏且默认隐藏；编辑保存保留首尾空格；生成后的密码重新默认遮蔽；空秘密提示改为“未填写”。
- 搜索与可访问性：补充同分结果最近使用排序、稳定次级顺序、命中字段 tooltip（HTML 转义）、辅助描述、50+ 条结果提示和全局搜索回归。
- 界面状态：splitter 在窗口显示后恢复，修复窗口几何未准备时 `restoreState()` 失败；动态编辑控件与错误提示增加 accessible name/主题语义色。
- 创建库提示：明确主密码无法恢复。
- 最终 33 模块 237/237 通过，固定构建后的 release EXE SHA-256 为 `88199a9ba872dc1c1af96376bb59b18946073a5a5af98d8917bb5bd54423ac44`。完整明细见 `CODEX_50_ITERATIONS.md`。

## 主窗口内重新解锁（2026-10-26）

- 锁定、空闲自动锁定和 Windows 会话锁定后，直接切换到主窗口内的密码输入页；保留当前 KDBX 完整路径，不要求重新选择文件。首次启动的库选择/创建窗口保持不变。
- 锁定时仍先清空搜索、账户列表、详情、搜索索引和本程序拥有的剪贴板内容；禁用工作区与窗口快捷键。错误密码在当前页面提示，正确密码在后台线程重新打开同一 KDBX 后恢复工作区。
- `tests/audit/test_runtime.py` 加入真实控件信号回归：锁定按钮切换页面、错误密码保持锁定、Enter 键正确解锁并恢复同一库。定向模块 **10/10 通过**；全量 **33 模块、239 passed、0 failed/errors/skipped**，Pex 自动选择 20 个 worker。明细见 `docs/inline-unlock-20261026/pytest-results-full-20261026.txt`。
- 固定构建 `--validate-only` 的 EXE 自检和真实桌面启动 smoke 通过，`--promote` 更新了 `release/Accnary.exe` 及 SHA sidecar。文件 46,112,129 字节，SHA-256：`5fb399239ce1e5aefa0dc7fdc292fdb5e2026a860ee6455734dce536146ef4f4`。
- 构建清理了 `build/`、`dist/`、pytest 缓存和 Python 缓存；Pex 临时 runner、隔离测试 KDBX 目录已删除。没有触碰项目数据库或 `release/data`。

## 分类切换闪动修复（2026-10-26）

- 根因：中等窗口宽度（760–999 px）下分类导航是临时展开的，点击分类会立刻收起侧栏并重排三栏；响应式更新还在每次调用时重复设置相同的可见状态。
- 修复：该宽度范围选择分类后保持导航展开，方便连续切换；窄屏（小于 760 px）仍在选择后收起导航。将侧栏、列表和详情的可见性更新限制在响应式布局确实变化时，避免无意义重排。
- 新增真实 Qt 点击回归：窗口 860 px 时展开导航并点击分类，侧栏保持可见、Splitter 尺寸不变。`tests/phase2/test_main_window.py` 定向模块 **9/9 通过**；全量 **33 模块、240 passed、0 failed/errors/skipped**，Pex 自动选择 20 个 worker。明细见 `docs/category-switch-20261026/pytest-results-full-20261026.txt`。
- 固定构建 `--validate-only`、真实桌面启动 smoke、EXE `--check` 与 `--promote` 均通过。release EXE 为 46,110,496 字节，SHA-256：`d831bb955f6e181413967f028c12d742db67b044ac05fb79f212dc7b175c1500`，sidecar 匹配。
- 构建中间文件、生成的 ICO、pytest 缓存、Python 缓存、Pex runner 和隔离测试库已清理；未触碰用户密码库。

## 分类悬浮小窗补充修复（2026-10-26）

- 删除侧栏分类项的账户数 tooltip（原内容为“X 个账户”），并移除分类项点状焦点框；分类选中态仍由背景色和文字色表达，避免鼠标经过/点击时出现短暂小窗和虚线闪现。
- 分类稳定性回归增加无 tooltip 断言。单项 Qt 点击测试通过；全量仍为 **33 模块、240 passed、0 failed/errors/skipped**，记录见 `docs/category-switch-final-20261026/pytest-results-full-20261026.txt`。
- 随后按固定构建流程完成 `build_exe.py --validate-only` 与 `--promote`；真实桌面启动 smoke、release EXE `--check` 均通过。最新 `release/Accnary.exe` 为 **46,110,897 字节**，SHA-256 `b6cd0e8100ca9228239e0a0fdbbe29f34e08a836308e9d227ccda079e4a488be`，sidecar 匹配。
- 构建目录、pytest/Python 缓存、生成的 `app-icon.ico`、临时 runner 与隔离测试库均已清理；没有终止运行中的程序或触碰用户密码库。

## 窄窗口分类切换二次复现与修复（2026-10-26）

- 用户反馈仍闪动后，补测发现之前只覆盖 860 Qt 逻辑像素，漏掉了 760 以下分支。Qt 控件点击在 535 逻辑像素下稳定复现：选分类会把 `_nav_open` 设为 false、收起侧栏；同一用例在 860 通过。
- 修复为分类切换时保持侧栏展开。窄屏选账户进入详情时仍按原逻辑切换到详情页。核心变化只在 `MainWindow._on_navigation_clicked`，不改存储和账户数据。
- 回归参数覆盖 535/860 逻辑像素：两次真实 Qt 控件点击均通过，splitter 尺寸不变；点击后等待 800 ms 检查没有可见 `QToolTip`。定向测试 2/2 通过。
- 全量回归由 Pex 一次调度 33 个独立测试模块：**241 passed、0 失败**；结果见 `docs/category-switch-repair-20261026/pytest-results-full-20261026.txt`。
- 固定构建脚本 `--validate-only`、真实窗口启动 smoke、EXE `--check` 与 `--promote` 均通过。最新 EXE 为 **46,109,272 字节**，SHA-256 `337df629e5e7841c9275c5a0552acc5f31827081f373cbbda859d86e61c7fa00`，sidecar 匹配。
- 进一步用旧版窄屏收起路径做了命中测试：分类点击时的全局坐标，在侧栏收起后落到账户列表的一条记录上，而该记录设置了完整信息 tooltip（`main_window.py` 的账户项 `setToolTip`）。这解释了小窗为何会跟着布局跳变出现；offscreen 测试不绘制真实桌面 tooltip，但已验证坐标命中和 tooltip 内容。
- 修复后侧栏不收起，点击坐标不再落到账户列表；回归同时断言列表项不在指针坐标下方，并等待 800 ms 确认没有可见 `QToolTip`。因此闪动和小窗的触发链都已有代码级修复与回归覆盖。
